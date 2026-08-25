"""FastAPI: living-room stage, async Generate, Piper wavs, /now-playing."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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

DATA_DIR.mkdir(parents=True, exist_ok=True)
TTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="The Singularity Blues", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
STAGE_DIR = Path(__file__).resolve().parent / "stage"
INDEX_HTML = STATIC_DIR / "index.html"

_mem: Memory | None = None
_episode_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_latest_job = ""


def get_mem() -> Memory:
    global _mem
    if _mem is None:
        _mem = seed()
    return _mem


def _job_snapshot(job_id: str) -> dict:
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    job.pop("packet", None)
    return job


class PromptIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class EpisodeIn(BaseModel):
    topic: str | None = Field(default=None, max_length=280)


@app.on_event("startup")
def _startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    get_mem()
    assembler = ROOT / "tools" / "assemble_web_engine.py"
    if assembler.is_file():
        subprocess.run([sys.executable, str(assembler)], check=False)


@app.get("/")
def index():
    if (STAGE_DIR / "index.html").is_file():
        return RedirectResponse(url="/stage/", status_code=307)
    if INDEX_HTML.is_file():
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<p>Singularity Blues. POST /episode</p>")


@app.get("/healthz")
def healthz() -> dict:
    wavs = list(TTS_DIR.glob("*.wav")) if TTS_DIR.is_dir() else []
    return {
        "ok": True,
        "writer": "gemini" if has_gemini_key() else "mock",
        "piper": piper_available(),
        "db": str(get_mem().db_path),
        "now_playing": NOW_PLAYING_PATH.is_file(),
        "stage": (STAGE_DIR / "index.html").is_file() and (STAGE_DIR / "index.wasm").is_file(),
        "tts_wavs": len(wavs),
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


@app.post("/episode")
def post_episode(body: EpisodeIn | None = None) -> dict:
    """Start a Gemini+Piper episode in the background. Poll GET /episode/status."""
    if not has_gemini_key():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not set")
    topic = (body.topic.strip() if body and body.topic else None) or None
    if topic == "":
        topic = None
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        global _latest_job
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "phase": "queued",
            "beat": 0,
            "beats": 0,
            "speaker": "",
            "episode_id": None,
            "topic": topic or "",
            "error": "",
        }
        _latest_job = job_id

    def _progress(update: dict) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            for key in ("phase", "beat", "beats", "speaker"):
                if key in update:
                    job[key] = update[key]

    def _work() -> None:
        try:
            _progress({"phase": "writing"})
            with _episode_lock:
                packet = run_episode(get_mem(), topic=topic, once=False, progress=_progress)
            with _jobs_lock:
                job = _jobs[job_id]
                job["status"] = "ready"
                job["phase"] = "ready"
                job["episode_id"] = packet.get("episode_id")
                job["topic"] = packet.get("topic") or job.get("topic") or ""
                job["beats"] = len(packet.get("beats") or [])
                job["beat"] = job["beats"]
        except Exception as exc:
            with _jobs_lock:
                job = _jobs[job_id]
                job["status"] = "error"
                job["phase"] = "error"
                job["error"] = f"{type(exc).__name__}: {exc}"

    threading.Thread(target=_work, daemon=True).start()
    return {"job_id": job_id, "status": "started"}


@app.get("/episode/status")
def episode_status(job_id: str | None = None) -> dict:
    jid = job_id or _latest_job
    if not jid:
        return {"id": None, "status": "idle", "phase": "idle", "beat": 0, "beats": 0, "speaker": "", "episode_id": None, "error": ""}
    snap = _job_snapshot(jid)
    if not snap:
        raise HTTPException(status_code=404, detail="unknown job")
    return snap


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


@app.get("/data/tts/{filename}")
def tts_wav(filename: str):
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="bad filename")
    path = TTS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="wav missing")
    return FileResponse(path, media_type="audio/wav", filename=filename)


@app.get("/stage/index.wasm")
def stage_wasm():
    path = STAGE_DIR / "index.wasm"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="stage wasm missing")
    return FileResponse(path, media_type="application/wasm")


@app.get("/history")
def history() -> dict:
    return {"episodes": get_mem().list_episodes(limit=30)}


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if STAGE_DIR.is_dir() and (STAGE_DIR / "index.html").is_file():
    app.mount("/stage", StaticFiles(directory=str(STAGE_DIR), html=True), name="stage")
