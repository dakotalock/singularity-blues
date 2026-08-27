"""Episode loop. `python -m orchestrator.loop` forever; `--once` for a single scene."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, load_dotenv
from orchestrator.gemini import PromptRefused, finalize_scene, get_condenser, get_writer, load_bible
from orchestrator.memory import Memory
from orchestrator.moderation import episode_title, prefilter, scrub_slurs
from orchestrator.schemas import validate_scene
from orchestrator.seed import seed
from orchestrator.selector import choose
from orchestrator.playlist import absorb as playlist_absorb
from orchestrator.playlist import pin as playlist_pin
from orchestrator.voice_queue import HIGH, voice_episode


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
    progress=None,
    username: str | None = None,
    paid: bool = False,
    refuse_reason: str | None = None,
    ltm_pin: bool = False,
    title: str | None = None,
    air: bool = True,
) -> dict[str, Any]:
    """
    1 collect prompts  2 prefilter  3 selector.choose
    4 memory.retrieve  5 write_scene  6 validate_schema
    7 voice_queue.voice_episode  8 memory.commit  9 playlist.pin/publish  10 print
    """
    source = "autonomous"
    used_ids: list[int] = []
    rejected_ids: list[tuple[int, str]] = []
    raw_topic = (topic or "").strip()

    if raw_topic:
        # Explicit topic from the stage UI ignores the queue and MUST be the episode.
        source = "seed" if once else "viewer"
        topic = raw_topic
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
                    if not refuse_reason:
                        refuse_reason = item.get("reason") or None
                    break
            else:
                used_ids = [int(p["id"]) for p in filtered.kept if p.get("id") is not None][:1]

    if once and not raw_topic and (source == "seed" or "toaster" in (topic or "").lower()):
        source = "seed" if not topic else source
        if not topic:
            topic = "Reed applies for toaster status"
            source = "seed"

    topic = (topic or "Reed applies for toaster status").strip()[:280]
    topic = scrub_slurs(topic)
    heading = title or episode_title(topic, username, refuse_reason=refuse_reason)
    retrieved = mem.retrieve(heading)
    bible = load_bible()
    writer = get_writer()
    if progress:
        progress({"phase": "writing", "beat": 0, "beats": 0, "speaker": ""})
    scene = writer.write_scene(
        bible,
        retrieved,
        retrieved,
        topic,
        source=source,
        username=username,
        paid=paid,
        refuse_reason=refuse_reason,
        title=heading,
    )
    if isinstance(scene, dict) and scene.get("refuse"):
        raise PromptRefused(scene.get("note") or "")
    scene = finalize_scene(scene, title=heading, source=source, username=username, paid=paid)

    episode_id = mem.insert_episode(heading, scene.get("source") or source, scene)
    packet = voice_episode(
        scene,
        episode_id,
        priority=HIGH,
        progress=progress,
        source=scene.get("source") or source,
    )
    condenser = get_condenser()
    condensation = condenser.condense(scene)
    mem.commit(condensation, episode_id=episode_id)
    if ltm_pin:
        mem.pin_episode(episode_id)

    if used_ids:
        mem.mark_prompts(used_ids, "used")
    for pid, reason in rejected_ids:
        mem.mark_prompts([pid], "rejected", reason)

    # Publishing is the final commit point. The player must not see an episode
    # while its request still reports writing/voicing. pin() owns the public air
    # queue; absorb() files a private showing into the library without hijacking
    # the broadcast loop.
    if air:
        playlist_pin(packet)
    else:
        playlist_absorb(packet)
    if progress:
        progress({"phase": "ready", "beat": len(packet.get("beats") or []), "beats": len(packet.get("beats") or []), "speaker": ""})

    print(f"episode_id={episode_id} topic={heading!r} source={scene.get('source') or source}")
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
