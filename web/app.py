"""FastAPI: living-room stage, async Generate, credits, /now-playing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, TTS_DIR, load_dotenv
from orchestrator import archive
from orchestrator.billing import create_checkout_session, handle_webhook, publishable_key
from orchestrator.credits import (
    BUNDLES,
    BUYER_COOKIE,
    OWNER_COOKIE,
    balance,
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
from orchestrator.gemini import has_gemini_key
from orchestrator.loop import run_episode
from orchestrator.memory import Memory
from orchestrator.moderation import episode_title, inspect, sanitize_display_name
from orchestrator.playlist import (
    board as playlist_board,
    current as playlist_current,
    ensure_voiced_boot,
    format_eta_copy,
    pin as playlist_pin,
    queued_wait_seconds,
    remaining_seconds,
    seconds_until_episode,
    snapshot as playlist_snapshot,
)
from orchestrator.seed import seed
from orchestrator.tts import piper_available

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
        if other.get("status") in ("error", "rejected"):
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
    job.pop("packet", None)
    if not job:
        return job
    job.update(_eta_for_job(job_id))
    return job


class PromptIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class EpisodeIn(BaseModel):
    topic: str | None = Field(default=None, max_length=280)
    username: str | None = Field(default=None, max_length=40)
    ltm_pin: bool = False


class CheckoutIn(BaseModel):
    bundle: str


class UnlockIn(BaseModel):
    secret: str = Field(min_length=1, max_length=200)


@app.on_event("startup")
def _startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    mem = get_mem()
    try:
        archive.init()
    except Exception:
        pass
    try:
        ensure_schema()
    except Exception:
        pass
    assembler = ROOT / "tools" / "assemble_web_engine.py"
    if assembler.is_file():
        subprocess.run([sys.executable, str(assembler)], check=False)

    def _boot_house() -> None:
        try:
            ensure_voiced_boot(mem)
        except Exception:
            pass

    threading.Thread(target=_boot_house, daemon=True, name="voiced-boot").start()


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
        "stripe": stripe_configured(),
    }


@app.get("/account")
def account(
    request: Request,
    response: Response,
    x_owner_secret: str | None = Header(default=None),
) -> dict:
    buyer_id = _buyer_id(request, response)
    owner = _is_owner(request, x_owner_secret)
    bal = balance(buyer_id)
    return {
        "credits": bal["credits"],
        "ltm_pins": bal["ltm_pins"],
        "owner": owner,
        "stripe": stripe_configured(),
        "publishable_key": publishable_key() if stripe_configured() else "",
        "bundles": [
            {"id": k, "usd": v["usd"], "credits": v["credits"], "pins": v["pins"], "label": v["label"]}
            for k, v in BUNDLES.items()
        ],
    }


@app.get("/unlock")
def unlock_page():
    if UNLOCK_HTML.is_file():
        return HTMLResponse(UNLOCK_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<form method='post' action='/unlock' style='font:16px sans-serif;padding:24px'>"
        "<input name='secret' type='password' placeholder='house key'/>"
        "<button type='submit'>Unlock</button></form>"
    )


@app.post("/unlock")
def unlock(body: UnlockIn, response: Response) -> dict:
    token = owner_cookie_value()
    if not is_owner(header=body.secret) or not token:
        raise HTTPException(status_code=403, detail="no")
    response.set_cookie(
        OWNER_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,
        path="/",
    )
    return {"ok": True, "owner": True}


@app.post("/checkout")
def checkout(
    body: CheckoutIn,
    request: Request,
    response: Response,
) -> dict:
    if not stripe_configured():
        raise HTTPException(status_code=503, detail="Checkout is not configured")
    if body.bundle not in BUNDLES:
        raise HTTPException(status_code=400, detail="unknown bundle")
    buyer_id = _buyer_id(request, response)
    base = (os.environ.get("PUBLIC_BASE_URL", "") or str(request.base_url)).strip().rstrip("/")
    try:
        session = create_checkout_session(
            buyer_id=buyer_id,
            bundle=body.bundle,
            success_url=f"{base}/stage/?paid=1",
            cancel_url=f"{base}/stage/?paid=0",
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Checkout could not start")
    url = session.get("url")
    if not url:
        raise HTTPException(status_code=502, detail="Checkout could not start")
    return {"url": url, "id": session.get("id")}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig = request.headers.get("stripe-signature") or request.headers.get("Stripe-Signature") or ""
    try:
        result = handle_webhook(payload, sig)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid webhook")
    return result


@app.post("/prompt")
def post_prompt(body: PromptIn) -> dict:
    check = inspect(body.text)
    mem = get_mem()
    if check.verdict == "reject":
        pid = mem.enqueue_prompt(body.text.strip()[:400], status="rejected", reason=check.reason)
        return {"id": pid, "status": "rejected", "reason": check.reason}
    pid = mem.enqueue_prompt(check.text, status="pending")
    return {"id": pid, "status": "pending", "reason": check.reason, "verdict": check.verdict}


@app.post("/episode")
def post_episode(
    request: Request,
    response: Response,
    body: EpisodeIn | None = None,
    x_owner_secret: str | None = Header(default=None),
) -> dict:
    """Start an episode in the background. Poll GET /episode/status."""
    if not has_gemini_key():
        raise HTTPException(status_code=503, detail="Writer is not configured")
    owner = _is_owner(request, x_owner_secret)
    buyer_id = _buyer_id(request, response)
    username = sanitize_display_name(
        body.username if body else None,
        default="Dakota" if owner else None,
    )
    if not username:
        raise HTTPException(status_code=400, detail="A display name is required.")
    topic = (body.topic.strip() if body and body.topic else None) or None
    if topic == "":
        topic = None
    if not topic:
        raise HTTPException(status_code=400, detail="A prompt is required.")

    check = inspect(topic)
    want_pin = bool(body and body.ltm_pin)
    spent = False
    pin_spent = False
    paid = False
    if not owner:
        if stripe_configured():
            if not spend_credit(buyer_id, 1):
                raise HTTPException(status_code=402, detail="Buy a prompt pack to ask the Selector.")
            spent = True
            paid = True
        if want_pin:
            if spend_pin(buyer_id, 1):
                pin_spent = True
            else:
                want_pin = False
    else:
        want_pin = bool(want_pin)

    if check.verdict == "reject":
        if spent:
            refund_credit(buyer_id, 1)
        if pin_spent:
            refund_pin(buyer_id, 1)
        bal = balance(buyer_id)
        return {
            "status": "rejected",
            "reason": check.reason,
            "refunded": True,
            "credits": bal["credits"],
            "ltm_pins": bal["ltm_pins"],
        }

    if check.verdict != "accept" and pin_spent:
        refund_pin(buyer_id, 1)
        pin_spent = False
        want_pin = False

    refuse_reason = check.reason if check.verdict == "refuse" else None
    writer_topic = check.text
    title = episode_title(writer_topic, username, refuse_reason=refuse_reason)
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
            "topic": title,
            "username": username,
            "paid": paid,
            "error": "",
            "credits": balance(buyer_id)["credits"],
        }
        _job_order.append(job_id)
        _latest_job = job_id
    eta = _eta_for_job(job_id)

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
                packet = run_episode(
                    get_mem(),
                    topic=writer_topic,
                    once=False,
                    progress=_progress,
                    username=username,
                    paid=paid,
                    refuse_reason=refuse_reason,
                    ltm_pin=want_pin,
                    title=title,
                )
                playlist_pin(packet)
            with _jobs_lock:
                job = _jobs[job_id]
                job["status"] = "ready"
                job["phase"] = "ready"
                job["episode_id"] = packet.get("episode_id")
                job["topic"] = packet.get("topic") or job.get("topic") or ""
                job["beats"] = len(packet.get("beats") or [])
                job["beat"] = job["beats"]
        except Exception as exc:
            if spent:
                refund_credit(buyer_id, 1)
            if pin_spent:
                refund_pin(buyer_id, 1)
            with _jobs_lock:
                job = _jobs[job_id]
                job["status"] = "error"
                job["phase"] = "error"
                job["error"] = f"{type(exc).__name__}: {exc}"

    threading.Thread(target=_work, daemon=True).start()
    return {
        "job_id": job_id,
        "status": "started",
        "topic": title,
        "username": username,
        "paid": paid,
        "credits": balance(buyer_id)["credits"],
        **eta,
    }


@app.get("/episode/status")
def episode_status(job_id: str | None = None) -> dict:
    jid = job_id or _latest_job
    if not jid:
        rem = remaining_seconds()
        return {
            "id": None,
            "status": "idle",
            "phase": "idle",
            "beat": 0,
            "beats": 0,
            "speaker": "",
            "episode_id": None,
            "error": "",
            "eta_seconds": rem,
            "eta_copy": (f"Now: {topic}" if (topic := _airing_topic()) else ""),
        }
    snap = _job_snapshot(jid)
    if not snap:
        raise HTTPException(status_code=404, detail="unknown job")
    return snap



@app.get("/queue")
def queue_board() -> dict:
    """Public now-playing + upcoming written episodes. Writing jobs are listed separately."""
    board = playlist_board()
    writing: list[dict] = []
    with _jobs_lock:
        for jid in _job_order:
            job = _jobs.get(jid) or {}
            if job.get("status") in ("error", "rejected", "ready"):
                continue
            title = str(job.get("topic") or "").strip()
            if not title:
                continue
            writing.append({"topic": title, "phase": job.get("phase") or "writing"})
    return {"now": board.get("now") or "", "queue": board.get("queue") or [], "writing": writing}


@app.get("/now-playing")
def now_playing() -> dict:
    packet = playlist_current()
    if packet.get("beats"):
        return packet
    if NOW_PLAYING_PATH.is_file():
        return json.loads(NOW_PLAYING_PATH.read_text(encoding="utf-8"))
    return {"episode_id": None, "scene": None, "topic": None, "beats": []}


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


@app.get("/playlist")
def playlist() -> dict:
    return playlist_snapshot()


@app.get("/history")
def history() -> dict:
    return {"episodes": get_mem().list_episodes(limit=30)}


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if STAGE_DIR.is_dir() and (STAGE_DIR / "index.html").is_file():
    app.mount("/stage", StaticFiles(directory=str(STAGE_DIR), html=True), name="stage")
