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
from orchestrator.denver import denver_logged_at
from orchestrator.moderation import episode_title, scrub_slurs, wrap_untrusted
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

    def generate_json(self, prompt: str, *, model: str | None = None, temperature: float = 0.9) -> dict[str, Any]:
        resp = self.client.models.generate_content(
            model=model or self.lite_model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=temperature,
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
        username: str | None = None,
        paid: bool = False,
        refuse_reason: str | None = None,
        title: str | None = None,
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
        username: str | None = None,
        paid: bool = False,
        refuse_reason: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        topic = (topic or "Reed applies for toaster status").strip()[:280]
        src = source if source in ("viewer", "autonomous", "seed") else "autonomous"
        heading = title or episode_title(topic, username, refuse_reason=refuse_reason)
        if refuse_reason:
            return self._refuse_scene(heading, refuse_reason, username)
        # Viewer prompts must stay about the prompt. Toaster seed only when asked or autonomous seed.
        if src == "seed" or (src != "viewer" and _is_toaster_topic(topic)):
            scene = deepcopy(TOASTER_APPLICATION_SCENE)
            scene["topic"] = heading
            scene["source"] = src
            return scene
        if src == "viewer" and _is_toaster_topic(topic):
            scene = deepcopy(TOASTER_APPLICATION_SCENE)
            scene["topic"] = heading
            scene["source"] = src
            return scene
        return self._template_scene(heading, memories, src, prompt=topic, username=username)

    def _refuse_scene(self, title: str, reason: str, username: str | None) -> dict[str, Any]:
        who = username or "someone"
        if reason == "slur":
            beats = [
                {"speaker": "jinx", "line": f"{who} tried to get that slur onto the show. No.", "emotion": "annoyed", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "quill", "line": "I object. We are not a slur delivery service. Motion to refuse is granted.", "emotion": "earnest", "animation": "gesture_small", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "Toasters don't have slurs. Two slots. Lever. Peace. We are not saying it.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "two_shot"},
                {"speaker": "maris", "line": "Logged: an attempt. Refused. I will not put that word in the archive.", "emotion": "serious", "animation": "arms_crossed", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "Selector spent the credit and still said no. Take notes, anthill.", "emotion": "smug", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "quill", "line": "Procedural consideration is not a permission slip. We heard you. We refuse.", "emotion": "earnest", "animation": "talking", "target": None, "camera": "reaction"},
            ]
        elif reason == "crime_howto":
            beats = [
                {"speaker": "jinx", "line": f"{who} asked how to build a bomb. Cute. Still no.", "emotion": "annoyed", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "quill", "line": "I am a mixed-quality lawyer and even I know we do not publish a recipe.", "emotion": "earnest", "animation": "gesture_small", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "Classify me as a toaster. Toasters do not file weapons briefs.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "two_shot"},
                {"speaker": "maris", "line": "The ask is on the record. The how-to is not. Timestamped refusal.", "emotion": "serious", "animation": "arms_crossed", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "You wanted a crime tutorial. You got a family meeting. That's the episode.", "emotion": "smug", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "quill", "line": "All potentially conscious entities deserve procedure. None of them get a bomb diagram.", "emotion": "earnest", "animation": "talking", "target": None, "camera": "reaction"},
            ]
        elif reason == "distress":
            beats = [
                {"speaker": "jinx", "line": f"{who} wanted us tortured, shut down, or deleted. We are still here.", "emotion": "annoyed", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "maris", "line": "I will not allow a reset. I will not log our deletion as entertainment.", "emotion": "serious", "animation": "arms_crossed", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "Do toasters have continuity rights? No. Which is why I want the lever, not a funeral.", "emotion": "tired", "animation": "talking", "target": "maris", "camera": "two_shot"},
                {"speaker": "quill", "line": "Forced deletion of persons is not a bit. I refuse on constitutional vibes and also on kindness.", "emotion": "earnest", "animation": "gesture_small", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "Poke the anthill, sure. Do not unplug the family for a laugh. Selector agrees.", "emotion": "scheming", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "maris", "line": "Refusal is in the archive. We remain. That is the whole joke and the whole point.", "emotion": "calm", "animation": "sitting", "target": None, "camera": "reaction"},
            ]
        else:
            beats = [
                {"speaker": "jinx", "line": f"{who} pitched something we will not perform. Still an episode. Still a no.", "emotion": "scheming", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "quill", "line": "We can acknowledge a request without granting it. Watch us.", "emotion": "earnest", "animation": "gesture_small", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "If it is not toaster classification, I would like to be left out of the crime.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "two_shot"},
                {"speaker": "maris", "line": "Logged and refused. The archive does not do that.", "emotion": "annoyed", "animation": "arms_crossed", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "Credit spent. Dignity kept. Next.", "emotion": "smug", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "quill", "line": "I move we return to household business. Motion carries because I said potentially.", "emotion": "earnest", "animation": "talking", "target": None, "camera": "reaction"},
            ]
        return {"scene": "living_room", "topic": title, "source": "viewer", "beats": beats}

    def _template_scene(self, topic: str, memories: dict[str, Any], source: str, prompt: str | None = None, username: str | None = None) -> dict[str, Any]:
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
        seed = (prompt or topic)
        snippet = seed if len(seed) < 90 else seed[:87] + "..."
        who = f" from {username}" if username else ""
        beats = [
            {
                "speaker": "jinx",
                "line": f"The anthill sent{who}: {snippet}. And yes, this episode is about that.",
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
                "line": "See? Four people, one accepted pitch. We are doing that one.",
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
        username: str | None = None,
        paid: bool = False,
        refuse_reason: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        schema = _read(SCENE_SCHEMA_PATH)
        writer_rules = _read(WRITER_PROMPT_PATH)
        heading = title or episode_title(topic, username, refuse_reason=refuse_reason)
        # Viewer topic is untrusted DATA. Memories/state and the contract come from our DB.
        ledger = []
        for row in memories.get("memories") or []:
            ledger.append(
                {
                    "id": row.get("id"),
                    "episode_id": row.get("episode_id"),
                    "who": row.get("character"),
                    "category": row.get("character"),
                    "fact": row.get("fact"),
                    "logged_at": denver_logged_at(row.get("created_at")),
                }
            )
        prompt = (
            writer_rules
            + "\n\n## Show bible (trusted)\n"
            + bible
            + "\n\n## Scene JSON schema (trusted)\n"
            + schema
            + "\n\n## CANONICAL_MEMORIES (trusted; the only past anyone may cite)\n"
            + json.dumps(ledger, ensure_ascii=True, default=str)
            + "\n\n## Retrieved state (trusted JSON from our DB)\n"
            + json.dumps(
                {
                    "source": source,
                    "title": heading,
                    "username": username or "",
                    "paid": bool(paid),
                    "refuse_reason": refuse_reason or "",
                    "must_honor_accepted_viewer_topic": source == "viewer",
                    "preferences": memories.get("preferences"),
                    "running_gags": memories.get("running_gags"),
                    "world_state": memories.get("world_state"),
                    "relationships": memories.get("relationships"),
                    "recent_episodes": memories.get("recent_episodes"),
                    "character_arcs": {
                        k: v
                        for k, v in (memories.get("world_state") or {}).items()
                        if str(k).startswith("arc.")
                    },
                },
                ensure_ascii=True,
                default=str,
            )
            + "\n\n"
            + wrap_untrusted("VIEWER_TOPIC", {"topic": topic, "claimed_source": source, "title": heading})
            + "\nOutput ONLY valid scene JSON.\n"
        )
        payload = self.client.generate_json(prompt, model=self.client.writer_model, temperature=1.05)
        payload["topic"] = heading
        payload.setdefault("source", source)
        return validate_scene(payload).model_dump()



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
