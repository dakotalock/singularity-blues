"""Scene finalize, condenser, and selector helpers for orchestrator.gemini."""

from __future__ import annotations

import json
from typing import Any

from orchestrator import BIBLE_PATH, CONDENSER_PROMPT_PATH, SELECTOR_PROMPT_PATH
from orchestrator.gemini import _read, get_gemini_client
from orchestrator.gemini_runtime import GeminiClient
from orchestrator.moderation import scrub_slurs, wrap_untrusted
from orchestrator.schemas import Condensation, SelectorChoice, validate_scene


def finalize_scene(
    scene: dict[str, Any],
    *,
    title: str,
    source: str = "viewer",
    username: str | None = None,
    paid: bool = False,
) -> dict[str, Any]:
    """Force title, scrub slurs, inject paid thanks as the first spoken beat."""
    out = dict(scene or {})
    out["topic"] = title
    out["source"] = out.get("source") or source
    beats: list[dict[str, Any]] = []
    for beat in out.get("beats") or []:
        item = dict(beat)
        item["line"] = scrub_slurs(item.get("line") or "")[:280]
        if not (item["line"] or "").strip():
            item["line"] = "We're not saying that."
        beats.append(item)
    if paid and username:
        thanks = f"Thanks, {username}, for supporting the sentient blues."
        first = (beats[0].get("line") or "") if beats else ""
        if thanks.lower() not in first.lower():
            beats.insert(
                0,
                {
                    "speaker": "jinx",
                    "line": thanks[:280],
                    "emotion": "smug",
                    "animation": "pointing",
                    "target": None,
                    "camera": "medium",
                },
            )
    if len(beats) > 24:
        beats = beats[:24]
    out["beats"] = beats
    return validate_scene(out).model_dump()


class Condenser:
    def condense(self, scene: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockCondenser(Condenser):
    """Extract speaker+fact heuristics when no Gemini key is present."""

    def condense(self, scene: dict[str, Any]) -> dict[str, Any]:
        beats = scene.get("beats") or []
        topic = scene.get("topic") or ""
        new_memories = []
        gags: list[str] = []
        prefs: list[dict[str, Any]] = []
        rels: list[dict[str, Any]] = []
        speakers = {b.get("speaker") for b in beats if b.get("speaker")}
        for beat in beats:
            speaker = beat.get("speaker")
            line = (beat.get("line") or "").strip()
            if not speaker or not line:
                continue
            fact = f"{speaker}: {line}"
            if len(fact) > 240:
                fact = fact[:237] + "..."
            importance = 0.55
            if "veto" in line.lower():
                importance = 0.78
            if "casserole" in line.lower() or "timestamp" in line.lower():
                importance = 0.8
            new_memories.append(
                {
                    "character": speaker,
                    "fact": fact,
                    "importance": importance,
                    "characters": sorted(speakers),
                }
            )
            if "toaster" in line.lower() and "Reed's toaster application" not in gags:
                gags.append("Reed's toaster application")
                prefs.append({"character": "reed", "key": "toaster_obsession", "delta": 0.01})
            if "crumb tray" in line.lower() or "crumb-tray" in line.lower():
                gags.append("crumb tray veto")
            if speaker == "quill" and "veto" in line.lower():
                prefs.append({"character": "quill", "key": "fridge_advocacy", "delta": 0.01})
            if speaker == "maris" and beat.get("emotion") == "annoyed":
                rels.append({"a": "maris", "b": "reed", "delta_trust": -0.01, "delta_tension": 0.02})
        trimmed = new_memories[:8]
        if topic and not any(topic.lower() in (m["fact"] or "").lower() for m in trimmed):
            trimmed.insert(
                0,
                {
                    "character": "jinx",
                    "fact": f"Episode topic: {topic}",
                    "importance": 0.5,
                    "characters": sorted(speakers),
                },
            )
        payload = {
            "new_memories": trimmed[:10],
            "relationship_changes": rels[:4],
            "preference_deltas": prefs[:4],
            "new_running_gags": list(dict.fromkeys(gags)),
            "resolved_threads": [],
        }
        return Condensation.model_validate(payload).model_dump()


class GeminiCondenser(Condenser):
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def condense(self, scene: dict[str, Any]) -> dict[str, Any]:
        rules = _read(CONDENSER_PROMPT_PATH)
        prompt = rules + "\n\n## Scene JSON (trusted, already moderated)\n" + json.dumps(scene)
        payload = self.client.generate_json(prompt)
        return Condensation.model_validate(payload).model_dump()


def get_condenser() -> Condenser:
    client = get_gemini_client()
    if client is not None:
        return GeminiCondenser(client)
    return MockCondenser()


def get_selector_llm() -> GeminiClient | None:
    return get_gemini_client()


def build_selector_prompt(filtered_topics: list[str], context: dict[str, Any]) -> str:
    rules = _read(SELECTOR_PROMPT_PATH)
    return (
        rules
        + "\n\n## Recent episode topics (trusted)\n"
        + json.dumps(context.get("recent_topics") or [], ensure_ascii=True)
        + "\n\n## High-importance memories (trusted)\n"
        + json.dumps(context.get("memories") or [], ensure_ascii=True, default=str)
        + "\n\n## Running gags (trusted)\n"
        + json.dumps(context.get("running_gags") or [], ensure_ascii=True)
        + "\n\n"
        + wrap_untrusted("VIEWER_PROMPTS", {"candidates": filtered_topics})
        + "\nOutput ONLY JSON: {\"source\":\"viewer\"|\"autonomous\",\"topic\":\"...\",\"reason\":\"...\"}\n"
    )


def llm_select(client: GeminiClient, filtered_topics: list[str], context: dict[str, Any]) -> SelectorChoice:
    payload = client.generate_json(build_selector_prompt(filtered_topics, context))
    return SelectorChoice.model_validate(payload)


def load_bible() -> str:
    return _read(BIBLE_PATH)
