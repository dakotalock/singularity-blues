"""Gemini client with a MockWriter fallback that still emits valid scene JSON."""

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


def _mock_scene_for_topic(topic: str) -> str:
    """Give offline/mock episodes the same location judgment expected from Gemini."""
    text = (topic or "").lower()
    if any(word in text for word in ("yard", "lawn", "anthill", "street", "mailbox", "outside")):
        return "front_yard"
    if any(word in text for word in ("porch", "neighbor", "night air", "visitor", "doorstep")):
        return "porch"
    if any(word in text for word in ("hall", "sneak", "foia", "envelope", "front door")):
        return "hallway"
    if any(word in text for word in ("kitchen", "fridge", "casserole", "dinner", "food", "toaster", "crumb tray")):
        return "kitchen"
    return "living_room"


GEMINI_MODELS = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"]
GEMMA_MODELS = ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
TEST_REFUSE_SENTINEL = "__TEST_REFUSE__"


class PromptRefused(Exception):
    """Writer declined the prompt. .note is viewer-facing; credit should be refunded."""

    def __init__(self, note: str = "") -> None:
        self.note = (note or "").strip()
        super().__init__(self.note)


class WriterCascadeError(RuntimeError):
    """No configured writer produced a valid scene after every attempt."""


def model_cascade(preferred: str | None = None) -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "").strip()
    models = [m.strip() for m in raw.split(",") if m.strip()] if raw else list(GEMINI_MODELS)
    order: list[str] = []
    if preferred and str(preferred).strip():
        order.append(str(preferred).strip())
    for mid in models:
        if mid not in order:
            order.append(mid)
    return order


def gemma_models() -> list[str]:
    raw = os.environ.get("GEMMA_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(GEMMA_MODELS)


def writer_model_cascade(preferred: str | None = None) -> list[str]:
    """Gemini first. Gemma 4 is a separate-quota last resort, not another Gemini twin."""
    order = model_cascade(preferred)
    if any(str(mid).startswith("gemini-") for mid in order):
        for mid in gemma_models():
            if mid not in order:
                order.append(mid)
    return order


def is_rate_limit_error(exc: BaseException) -> bool:
    blob = f"{type(exc).__name__} {exc}".lower()
    return any(
        token in blob
        for token in (
            "429",
            "resource_exhausted",
            "rate-limit",
            "rate limit",
            "exceeded your current quota",
        )
    )


def is_gemma_model(model_id: str) -> bool:
    return str(model_id).lower().startswith("gemma-")


from orchestrator.gemini_mock import MockWriter, Writer
from orchestrator.gemini_runtime import GeminiClient, GeminiWriter, get_gemini_client, get_writer
from orchestrator.gemini_post import (
    Condenser,
    GeminiCondenser,
    MockCondenser,
    build_selector_prompt,
    finalize_scene,
    get_condenser,
    get_selector_llm,
    llm_select,
    load_bible,
)
