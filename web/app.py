"""FastAPI: POST /prompt, GET /now-playing, /characters, /memories, /history, /healthz."""

from __future__ import annotations

import json
import os
from pathlib import Path

import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, TTS_DIR, load_dotenv
from orchestrator.gemini import has_gemini_key
from orchestrator.loop import run_episode
from orchestrator.memory import Memory
from orchestrator.moderation import inspect
from orchestrator.seed import seed
from orchestrator.tts import piper_available

load_dotenv()

app = FastAPI(title="The Singularity Blues", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

_mem: Memory | None = None
_episode_lock = threading.Lock()


def get_mem() -> Memory:
    global _mem
    if _mem is None:
        _mem = seed()
    return _mem


class PromptIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@app.on_event("startup")
def _startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    get_mem()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if INDEX_HTML.is_file():
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<p>Singularity Blues. POST /prompt</p>")


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "writer": "gemini" if has_gemini_key() else "mock",
        "piper": piper_available(),
        "db": str(get_mem().db_path),
        "now_playing": NOW_PLAYING_PATH.is_file(),
    }


@app.post("/prompt")
def post_prompt(body: PromptIn) -> dict:
    check = inspect(body.text)
    mem = get_mem()
    if not check.ok:
        pid = mem.enqueue_prompt(body.text.strip()[:400], status="rejected", reason=check.reason)
        return {"id": pid, "status": "rejected", "reason": check.reason}
    pid = mem.enqueue_prompt(check.text, status="pending")
    return {"id": pid, "status": "pending", "reason": ""}


class EpisodeIn(BaseModel):
    topic: str | None = Field(default=None, max_length=280)


@app.post("/episode")
def post_episode(body: EpisodeIn | None = None) -> dict:
    """One tap: Gemini writes a new episode. Dakota is the only user."""
    if not has_gemini_key():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not set")
    topic = (body.topic.strip() if body and body.topic else None) or None
    if topic == "":
        topic = None
    try:
        with _episode_lock:
            packet = run_episode(get_mem(), topic=topic, once=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"episode failed: {type(exc).__name__}") from exc
    return {
        "episode_id": packet.get("episode_id"),
        "topic": packet.get("topic"),
        "source": packet.get("source"),
        "writer": "gemini",
        "beats": packet.get("beats") or [],
    }


@app.get("/now-playing")
def now_playing() -> dict:
    if not NOW_PLAYING_PATH.is_file():
        return {"episode_id": None, "scene": None, "topic": None, "beats": []}
    return json.loads(NOW_PLAYING_PATH.read_text(encoding="utf-8"))


@app.get("/characters")
def characters() -> dict:
    return {"characters": get_mem().list_characters()}


@app.get("/memories")
def memories() -> dict:
    return {"memories": get_mem().list_memories(limit=50)}


@app.get("/history")
def history() -> dict:
    return {"episodes": get_mem().list_episodes(limit=30)}


if (DATA_DIR).is_dir():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
