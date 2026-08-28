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
