"""FastAPI: living-room stage, async Generate, credits, /now-playing."""

from __future__ import annotations

import hmac
import json
import re
import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, TTS_DIR, load_dotenv
from orchestrator import archive
from orchestrator import r2
from orchestrator import voice_queue
from orchestrator.billing import create_checkout_session, handle_webhook, publishable_key
from orchestrator.credits import (
    BUNDLES,
    BUYER_COOKIE,
    OWNER_COOKIE,
    balance,
    buyer_for_recovery_key,
    ensure_recovery_key,
    ensure_schema,
    is_owner,
    mint_buyer_id,
    owner_cookie_value,
    refund_credit,
    refund_pin,
    sign_buyer,
    spend_credit,
    spend_pin,
    stripe_configured,
    verify_buyer,
)
from orchestrator.gemini import PromptRefused, WriterCascadeError, has_gemini_key
from orchestrator.loop import run_episode
from orchestrator.memory import Memory
from orchestrator.moderation import episode_title, inspect, sanitize_display_name
from orchestrator.playlist import (
    board as playlist_board,
    current as playlist_current,
    ensure_voiced_boot,
    format_eta_copy,
    queued_wait_seconds,
    remaining_seconds,
    seconds_until_episode,
    snapshot as playlist_snapshot,
)
from orchestrator.seed import seed
from orchestrator.tts import piper_available
from orchestrator.writer_cascade import DEFAULT_VETO_NOTE

load_dotenv()

DATA_DIR.mkdir(parents=True, exist_ok=True)
TTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="The Singularity Blues", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
STAGE_DIR = Path(__file__).resolve().parent / "stage"
INDEX_HTML = STATIC_DIR / "index.html"
UNLOCK_HTML = STATIC_DIR / "unlock.html"

_mem: Memory | None = None
_episode_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_job_order: list[str] = []
_latest_job = ""
ESTIMATE_SEC = 90.0
JOB_RETENTION_SEC = 6 * 3600
MAX_RETAINED_JOBS = 2000


def _worker_setting(name: str, default: int, maximum: int) -> int:
    try:
        value = int((os.environ.get(name) or str(default)).strip())
    except ValueError:
        value = default
    return max(1, min(maximum, value))


# Public prompts retain their single on-air ordering lane. Private showings have a
# separate bounded pool, so public traffic cannot make them wait behind the shared
# queue and a traffic spike cannot create an unbounded number of OS threads.
_public_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="episode-public")
_private_executor = ThreadPoolExecutor(
    max_workers=_worker_setting("PRIVATE_SHOWING_WORKERS", 8, 32),
    thread_name_prefix="episode-private",
)


def get_mem() -> Memory:
    global _mem
    if _mem is None:
        _mem = seed()
    return _mem


def _attach_buyer_cookie(response: Response, buyer_id: str) -> None:
    response.set_cookie(
        BUYER_COOKIE,
        sign_buyer(buyer_id),
        httponly=True,
        samesite="lax",
        max_age=86400 * 400,
        path="/",
    )


def _buyer_id(request: Request, response: Response) -> str:
    token = request.cookies.get(BUYER_COOKIE)
    buyer_id = verify_buyer(token)
    if not buyer_id:
        buyer_id = mint_buyer_id()
    _attach_buyer_cookie(response, buyer_id)
    return buyer_id


def _is_owner(request: Request, header: str | None) -> bool:
    return is_owner(header=header, cookie=request.cookies.get(OWNER_COOKIE))


def _airing_topic() -> str:
    try:
        pkt = playlist_current() or {}
        return str(pkt.get("topic") or "").strip()
    except Exception:
        return ""


def _prune_jobs_locked(now: float | None = None) -> None:
    """Bound 24/7 job metadata while retaining recent status/packet polling."""
    stamp = time.time() if now is None else float(now)
    terminal = {"ready", "error", "rejected", "refused"}
    expired = [
        jid
        for jid, job in _jobs.items()
        if job.get("status") in terminal
        and stamp - float(job.get("finished_at") or job.get("created_at") or stamp) > JOB_RETENTION_SEC
    ]
    for jid in expired:
        _jobs.pop(jid, None)
    if len(_jobs) > MAX_RETAINED_JOBS:
        finished = sorted(
            (
                (float(job.get("finished_at") or job.get("created_at") or stamp), jid)
                for jid, job in _jobs.items()
                if job.get("status") in terminal
            )
        )
        for _finished_at, jid in finished[: max(0, len(_jobs) - MAX_RETAINED_JOBS)]:
            _jobs.pop(jid, None)
    _job_order[:] = [jid for jid in _job_order if jid in _jobs]


def _safe_refuse_note(note: str | None) -> str:
    raw = (note or "").strip()
    if not raw:
        return DEFAULT_VETO_NOTE
    text = raw.splitlines()[0].strip()
    if not text or len(text) > 180:
        return DEFAULT_VETO_NOTE
    if re.search(r"gemini|piper|gpt-?\d|claude|openai|google-genai", text, re.I):
        return DEFAULT_VETO_NOTE
    return text[:160]


def _public_job_error(exc: BaseException) -> str:
    if isinstance(exc, WriterCascadeError):
        return "The writer could not finish that episode."
    raw = f"{type(exc).__name__}: {exc}"
    if re.search(r"gemini-\d|gemini-3|piper", raw, re.I):
        return "The writer could not finish that episode."
    return raw[:240]


def _writing_copy(phase: str) -> str:
    now = _airing_topic()
    if phase == "speaking":
        base = "Casting voices. Not in the air queue yet."
    else:
        base = "Still writing. This scene keeps playing."
    if now:
        return f"Now: {now}. {base}"
    return base


def _eta_for_job(job_id: str) -> dict:
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
        order = list(_job_order)
    eid = job.get("episode_id")
    airing = _airing_topic()
    if job.get("private"):
        if job.get("status") == "ready":
            return {
                "eta_seconds": 0,
                "eta_copy": "Ready for you after this rerun. Also saved to the library and memory.",
                "position": 0,
                "current_topic": airing,
                "private": True,
            }
        phase = str(job.get("phase") or "writing")
        copy = "Writing your private showing. The public show keeps playing."
        if phase == "speaking":
            copy = "Casting voices for your private showing. The public show keeps playing."
        return {
            "eta_seconds": 0,
            "eta_copy": copy,
            "position": 0,
            "current_topic": airing,
            "private": True,
        }
    if job.get("status") == "ready" and eid:
        secs = float(seconds_until_episode(int(eid)))
        return {
            "eta_seconds": secs,
            "eta_copy": format_eta_copy(secs),
            "position": 0 if secs <= 8 else max(1, int(job.get("position") or 1)),
            "current_topic": airing,
        }
    wait = float(queued_wait_seconds())
    position = 1
    for jid in order:
        if jid == job_id:
            break
        other = _jobs.get(jid) or {}
        if other.get("status") in ("error", "rejected", "refused"):
            continue
        if other.get("status") == "ready" and other.get("episode_id"):
            continue
        wait += ESTIMATE_SEC
        position += 1
    phase = str(job.get("phase") or "writing")
    return {
        "eta_seconds": wait,
        "eta_copy": _writing_copy(phase),
        "position": position,
        "current_topic": airing,
    }


def _job_snapshot(job_id: str) -> dict:
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job.get("private"):
        job.pop("packet", None)
    job.pop("buyer_id", None)
    if not job:
        return job
    job.update(_eta_for_job(job_id))
    return job


def _viewer_private_packet(packet: dict) -> dict:
    """Unique play id for this browser only. Library keeps the real episode id."""
    out = deepcopy(packet or {})
    real = out.get("show_episode_id", out.get("episode_id"))
    out["show_episode_id"] = real
    try:
        base = int(real or 0)
    except (TypeError, ValueError):
        base = 0
    out["episode_id"] = 1_000_000 + (base % 900_000) + (int(time.time()) % 1000)
    out["private"] = True
    out["rerun"] = False
    return out


def _spawn_job(fn, *, concurrent: bool = False) -> None:
    """Return immediately through isolated, bounded public/private worker pools."""
    executor = _private_executor if concurrent else _public_executor
    executor.submit(fn)


class PromptIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class EpisodeIn(BaseModel):
    topic: str | None = Field(default=None, max_length=280)
    username: str | None = Field(default=None, max_length=40)
    ltm_pin: bool = False
    private_showing: bool = False


from web.routes import register

register(app)
