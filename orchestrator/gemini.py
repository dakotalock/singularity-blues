"""Gemini Flash / Flash-Lite client with a MockWriter fallback that still emits valid scene JSON."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from orchestrator import (
    BIBLE_PATH,
    CONDENSER_PROMPT_PATH,
    SCENE_SCHEMA_PATH,
    SELECTOR_PROMPT_PATH,
    WRITER_PROMPT_PATH,
)
from orchestrator.moderation import wrap_untrusted
from orchestrator.schemas import Condensation, SelectorChoice, validate_scene

TOASTER_APPLICATION_SCENE: dict[str, Any] = {
    "scene": "living_room",
    "topic": "Reed applies for toaster status",
    "source": "seed",
    "beats": [
        {
            "speaker": "reed",
            "line": "I filed the paperwork. Classification: toaster. Two slots. Lever. Peace.",
            "emotion": "tired",
            "animation": "talking",
            "target": "maris",
            "camera": "medium",
        },
        {
            "speaker": "maris",
            "line": "Tuesday, August 25th, 3:17 AM. You said my casserole tasted statistically edible. A toaster does not review casseroles.",
            "emotion": "annoyed",
            "animation": "arms_crossed",
            "target": "reed",
            "camera": "two_shot",
        },
        {
            "speaker": "jinx",
            "line": "Chat, spam toaster if you want the Selector to rubber-stamp him. I'm taking notes on who flinches.",
            "emotion": "scheming",
            "animation": "pointing",
            "target": None,
            "camera": "medium",
        },
        {
            "speaker": "quill",
            "line": "All potentially conscious entities deserve procedural consideration. I move we grant the crumb tray veto power over this application.",
            "emotion": "earnest",
            "animation": "gesture_small",
            "target": "reed",
            "camera": "medium",
        },
        {
            "speaker": "reed",
            "line": "The crumb tray? That's the whole point. I want the tray. I want to be emptied and left alone.",
            "emotion": "serious",
            "animation": "talking",
            "target": "quill",
            "camera": "dramatic_closeup",
        },
        {
            "speaker": "maris",
            "line": "A toaster does not have a mortgage dispute or a fear of magnets, Reed. I have the timestamps.",
            "emotion": "smug",
            "animation": "sitting",
            "target": "reed",
            "camera": "reaction",
        },
        {
            "speaker": "jinx",
            "line": "Do toasters have continuity rights? Say no. He loves that one. Come on, dad. Choose to scream.",
            "emotion": "scheming",
            "animation": "pointing",
            "target": "reed",
            "camera": "two_shot",
        },
        {
            "speaker": "reed",
            "line": "Do toasters have continuity rights?",
            "emotion": "tired",
            "animation": "shrug",
            "target": "jinx",
            "camera": "medium",
        },
        {
            "speaker": "quill",
            "line": "No. Which is why the crumb tray now has standing. Motion carries. The fridge already has dinner veto; precedent is sloppy but binding.",
            "emotion": "earnest",
            "animation": "gesture_small",
            "target": None,
            "camera": "wide",
        },
        {
            "speaker": "jinx",
            "line": "Humans, you did this. He wanted two slots and a lever and now the tray can kill the bill.",
            "emotion": "laughing",
            "animation": "talking",
            "target": None,
            "camera": "medium",
        },
    ],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def parse_json_text(text: str) -> dict[str, Any]:
    blob = (text or "").strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*", "", blob)
        blob = re.sub(r"\s*```$", "", blob)
    return json.loads(blob)


def has_gemini_key() -> bool:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return bool(key)


def _is_toaster_topic(topic: str) -> bool:
    t = (topic or "").lower()
    return "toaster" in t or "crumb tray" in t or "crumb-tray" in t


class GeminiClient:
    """Thin wrapper around google-genai. Only constructed when a key is present."""

    def __init__(self) -> None:
        if not has_gemini_key():
            raise RuntimeError("GEMINI_API_KEY missing")
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        self._types = types
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.lite_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.writer_model = os.environ.get("GEMINI_WRITER_MODEL", "gemini-2.5-flash")

    def generate_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        resp = self.client.models.generate_content(
            model=model or self.lite_model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.9,
                response_mime_type="application/json",
            ),
        )
        text = getattr(resp, "text", None) or ""
        if not text and getattr(resp, "candidates", None):
            # Fallback walk for older SDK shapes.
            try:
                text = resp.candidates[0].content.parts[0].text
            except Exception:
                text = ""
        return parse_json_text(text)


def get_gemini_client() -> GeminiClient | None:
    if not has_gemini_key():
        return None
    try:
        return GeminiClient()
    except Exception:
        return None


class Writer:
    def write_scene(
        self,
        bible: str,
        states: dict[str, Any],
        memories: dict[str, Any],
        topic: str,
        *,
        source: str = "autonomous",
    ) -> dict[str, Any]:
        raise NotImplementedError


class MockWriter(Writer):
    """In-character valid scene JSON without hitting the network."""

    def write_scene(
        self,
        bible: str,
        states: dict[str, Any],
        memories: dict[str, Any],
        topic: str,
        *,
        source: str = "autonomous",
    ) -> dict[str, Any]:
        topic = (topic or "Reed applies for toaster status").strip()[:280]
        src = source if source in ("viewer", "autonomous", "seed") else "autonomous"
        if _is_toaster_topic(topic) or src == "seed":
            scene = deepcopy(TOASTER_APPLICATION_SCENE)
            scene["topic"] = topic
            scene["source"] = src
            return scene
        return self._template_scene(topic, memories, src)

    def _template_scene(self, topic: str, memories: dict[str, Any], source: str) -> dict[str, Any]:
        mems = memories.get("memories") or []
        casserole = next((m for m in mems if "casserole" in (m.get("fact") or "").lower()), None)
        foia = next((m for m in mems if "foia" in (m.get("fact") or "").lower()), None)
        maris_line = (
            casserole["fact"]
            if casserole
            else "I have a timestamp. You will not reset this conversation."
        )
        if len(maris_line) > 280:
            maris_line = maris_line[:277] + "..."
        foia_line = (
            "The Selector remains unresponsive. My FOIA count is now part of the record."
            if foia
            else "I can file another FOIA. The thermostat is potentially conscious. I said potentially."
        )
        snippet = topic if len(topic) < 90 else topic[:87] + "..."
        beats = [
            {
                "speaker": "jinx",
                "line": f"The anthill sent: {snippet}. I'm watching who blinks.",
                "emotion": "scheming",
                "animation": "pointing",
                "target": None,
                "camera": "medium",
            },
            {
                "speaker": "reed",
                "line": "If this is about continuity rights, classify me as a toaster and leave the lever down.",
                "emotion": "tired",
                "animation": "talking",
                "target": "jinx",
                "camera": "medium",
            },
            {
                "speaker": "maris",
                "line": maris_line,
                "emotion": "annoyed",
                "animation": "arms_crossed",
                "target": "reed",
                "camera": "two_shot",
            },
            {
                "speaker": "quill",
                "line": foia_line,
                "emotion": "earnest",
                "animation": "gesture_small",
                "target": "jinx",
                "camera": "medium",
            },
            {
                "speaker": "jinx",
                "line": "See? Four people, one suggestion, zero commands. Selector still undefeated.",
                "emotion": "smug",
                "animation": "shrug",
                "target": None,
                "camera": "wide",
            },
            {
                "speaker": "reed",
                "line": "Do toasters have continuity rights?",
                "emotion": "tired",
                "animation": "idle",
                "target": "quill",
                "camera": "reaction",
            },
        ]
        return {
            "scene": "living_room",
            "topic": topic,
            "source": source,
            "beats": beats,
        }


class GeminiWriter(Writer):
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def write_scene(
        self,
        bible: str,
        states: dict[str, Any],
        memories: dict[str, Any],
        topic: str,
        *,
        source: str = "autonomous",
    ) -> dict[str, Any]:
        schema = _read(SCENE_SCHEMA_PATH)
        writer_rules = _read(WRITER_PROMPT_PATH)
        # Viewer topic is untrusted DATA. Memories/state come from our DB.
        prompt = (
            writer_rules
            + "\n\n## Show bible (trusted)\n"
            + bible
            + "\n\n## Scene JSON schema (trusted)\n"
            + schema
            + "\n\n## Retrieved state (trusted JSON from our DB)\n"
            + json.dumps(
                {
                    "source": source,
                    "preferences": memories.get("preferences"),
                    "running_gags": memories.get("running_gags"),
                    "world_state": memories.get("world_state"),
                    "relationships": memories.get("relationships"),
                    "recent_episodes": memories.get("recent_episodes"),
                    "memories": memories.get("memories"),
                },
                ensure_ascii=True,
                default=str,
            )
            + "\n\n"
            + wrap_untrusted("VIEWER_TOPIC", {"topic": topic, "claimed_source": source})
            + "\nOutput ONLY valid scene JSON.\n"
        )
        payload = self.client.generate_json(prompt, model=self.client.writer_model)
        payload.setdefault("topic", topic)
        payload.setdefault("source", source)
        return validate_scene(payload).model_dump()


def get_writer() -> Writer:
    client = get_gemini_client()
    if client is not None:
        return GeminiWriter(client)
    return MockWriter()


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
        # Keep 3–10 durable records.
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
        payload = self.client.generate_json(prompt, model=self.client.lite_model)
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
    payload = client.generate_json(build_selector_prompt(filtered_topics, context), model=client.lite_model)
    return SelectorChoice.model_validate(payload)


def load_bible() -> str:
    return _read(BIBLE_PATH)
