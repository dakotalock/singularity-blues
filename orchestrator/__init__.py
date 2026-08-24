"""The Singularity Blues — 24/7 original-IP AI sitcom orchestrator."""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "0.1.0"

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
TTS_DIR = DATA_DIR / "tts"
VOICES_DIR = ROOT / "tts" / "voices"
PIPER_BIN = ROOT / "tools" / "piper" / "piper"
DB_PATH = DATA_DIR / "singularity_blues.db"
NOW_PLAYING_PATH = DATA_DIR / "now_playing.json"
BIBLE_PATH = PROMPTS_DIR / "show_bible.md"
WRITER_PROMPT_PATH = PROMPTS_DIR / "writer.md"
SELECTOR_PROMPT_PATH = PROMPTS_DIR / "selector.md"
CONDENSER_PROMPT_PATH = PROMPTS_DIR / "memory_condenser.md"
SCENE_SCHEMA_PATH = PROMPTS_DIR / "scene.schema.json"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding real env vars. Never prints values."""
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()
