"""Episode loop. `python -m orchestrator.loop` forever; `--once` for a single scene."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, load_dotenv
from orchestrator.gemini import get_condenser, get_writer, load_bible
from orchestrator.memory import Memory
from orchestrator.moderation import prefilter
from orchestrator.schemas import validate_scene
from orchestrator.seed import seed
from orchestrator.selector import choose
from orchestrator.tts import render, write_now_playing


def _context(mem: Memory) -> dict[str, Any]:
    retrieved = mem.retrieve("household", limit=8)
    return {
        "recent_topics": [e["topic"] for e in retrieved.get("recent_episodes") or []],
        "memories": retrieved.get("memories") or [],
        "running_gags": retrieved.get("running_gags") or [],
        "recent_prompt_texts": mem.recent_prompt_texts(),
    }


def run_episode(
    mem: Memory,
    *,
    topic: str | None = None,
    once: bool = False,
) -> dict[str, Any]:
    """
    1 collect prompts  2 prefilter  3 selector.choose
    4 memory.retrieve  5 write_scene  6 validate_schema
    7 tts.render  8 sidecar now_playing.json  9 memory.commit  10 print
    """
    source = "autonomous"
    used_ids: list[int] = []
    rejected_ids: list[tuple[int, str]] = []

    if topic:
        # Explicit --topic ignores the queue.
        source = "seed" if once else "viewer"
    else:
        prompts = mem.pending_prompts()
        filtered = prefilter(prompts, recent_texts=mem.recent_prompt_texts())
        for rej in filtered.rejected:
            if rej.prompt_id is not None:
                rejected_ids.append((rej.prompt_id, rej.reason))
        choice = choose(filtered, _context(mem), already_filtered=True)
        topic = choice.topic
        source = choice.source
        if source == "viewer":
            for item in filtered.kept:
                if item.get("text") == topic and item.get("id") is not None:
                    used_ids.append(int(item["id"]))
                    break
            else:
                used_ids = [int(p["id"]) for p in filtered.kept if p.get("id") is not None][:1]

    if once and (source == "seed" or "toaster" in (topic or "").lower()):
        source = "seed" if not topic else source
        if not topic:
            topic = "Reed applies for toaster status"
            source = "seed"

    topic = (topic or "Reed applies for toaster status").strip()[:280]
    retrieved = mem.retrieve(topic)
    bible = load_bible()
    writer = get_writer()
    scene = writer.write_scene(bible, retrieved, retrieved, topic, source=source)
    scene = validate_scene(scene).model_dump()

    episode_id = mem.insert_episode(topic, scene.get("source") or source, scene)
    packet = render(scene, episode_id)
    write_now_playing(packet)

    condenser = get_condenser()
    condensation = condenser.condense(scene)
    mem.commit(condensation, episode_id=episode_id)

    if used_ids:
        mem.mark_prompts(used_ids, "used")
    for pid, reason in rejected_ids:
        mem.mark_prompts([pid], "rejected", reason)

    print(f"episode_id={episode_id} topic={topic!r} source={scene.get('source') or source}")
    print(f"now_playing={NOW_PLAYING_PATH} beats={len(packet['beats'])}")
    return packet


def loop_forever(interval: float = 2.0) -> None:
    mem = seed()
    while True:
        packet = run_episode(mem)
        total = sum(b.get("duration_sec") or 1.0 for b in packet.get("beats") or [])
        time.sleep(max(interval, total + 1.5))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="The Singularity Blues episode loop")
    parser.add_argument("--once", action="store_true", help="run a single scene and exit")
    parser.add_argument("--topic", type=str, default=None, help="ignore the queue and use this topic")
    parser.add_argument("--interval", type=float, default=2.0, help="minimum gap between episodes")
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    mem = seed()
    if args.once:
        run_episode(mem, topic=args.topic, once=True)
        return 0
    try:
        loop_forever(interval=args.interval)
    except KeyboardInterrupt:
        print("stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
