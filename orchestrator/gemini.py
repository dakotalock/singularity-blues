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
