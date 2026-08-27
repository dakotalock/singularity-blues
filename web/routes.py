"""Stage HTTP routes. Registered from web.app after helpers exist."""

import hmac
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from orchestrator.billing import create_checkout_session, handle_webhook, publishable_key
from orchestrator.credits import (
    BUNDLES,
    OWNER_COOKIE,
    balance,
    buyer_for_recovery_key,
    ensure_recovery_key,
    ensure_schema,
    is_owner,
    owner_cookie_value,
    refund_credit,
    refund_pin,
    spend_credit,
    spend_pin,
    stripe_configured,
)
from orchestrator.gemini import PromptRefused, has_gemini_key
from orchestrator.loop import run_episode
from orchestrator.moderation import episode_title, inspect, sanitize_display_name
from orchestrator.playlist import (
    board as playlist_board,
    current as playlist_current,
    ensure_voiced_boot,
    remaining_seconds,
    snapshot as playlist_snapshot,
)
from orchestrator import archive
from orchestrator import r2
from orchestrator import voice_queue
from orchestrator.tts import piper_available
from web.episode_routes import register_episode


def register(app):
    import web.app as m

    class CheckoutIn(BaseModel):
        bundle: str

    class UnlockIn(BaseModel):
        secret: str = Field(min_length=1, max_length=200)

    class RecoverIn(BaseModel):
        key: str = Field(min_length=1, max_length=200)

    @app.on_event("startup")
    def _startup() -> None:
        m.DATA_DIR.mkdir(parents=True, exist_ok=True)
        m.TTS_DIR.mkdir(parents=True, exist_ok=True)
        mem = m.get_mem()
        try:
            archive.init()
        except Exception:
            pass
        try:
            ensure_schema()
        except Exception:
            pass
        assembler = m.ROOT / "tools" / "assemble_web_engine.py"
        if assembler.is_file():
            subprocess.run([sys.executable, str(assembler)], check=False)

        voice_queue.start()

        def _boot_house() -> None:
            try:
                ensure_voiced_boot(mem)
            except Exception:
                pass

        threading.Thread(target=_boot_house, daemon=True, name="voiced-boot").start()

    @app.get("/")
    def index():
        if (m.STAGE_DIR / "index.html").is_file():
            return RedirectResponse(url="/stage/", status_code=307)
        if m.INDEX_HTML.is_file():
            return HTMLResponse(m.INDEX_HTML.read_text(encoding="utf-8"))
        return HTMLResponse("<p>Singularity Blues. POST /episode</p>")

    @app.get("/healthz")
    def healthz() -> dict:
        wavs = list(m.TTS_DIR.glob("*.wav")) if m.TTS_DIR.is_dir() else []
        return {
            "ok": True,
            "writer": "gemini" if m.has_gemini_key() else "mock",
            "piper": piper_available(),
            "db": str(m.get_mem().db_path),
            "now_playing": m.NOW_PLAYING_PATH.is_file(),
            "stage": (m.STAGE_DIR / "index.html").is_file() and (m.STAGE_DIR / "index.wasm").is_file(),
            "tts_wavs": len(wavs),
            "stripe": stripe_configured(),
        }

    @app.get("/account")
    def account(
        request: Request,
        response: Response,
        x_owner_secret: str | None = Header(default=None),
    ) -> dict:
        buyer_id = m._buyer_id(request, response)
        owner = m._is_owner(request, x_owner_secret)
        bal = balance(buyer_id)
        recovery_key = ensure_recovery_key(buyer_id)
        return {
            "credits": bal["credits"],
            "ltm_pins": bal["ltm_pins"],
            "owner": owner,
            "stripe": stripe_configured(),
            "publishable_key": publishable_key() if stripe_configured() else "",
            "recovery_key": recovery_key or "",
            "bundles": [
                {"id": k, "usd": v["usd"], "credits": v["credits"], "pins": v["pins"], "label": v["label"]}
                for k, v in BUNDLES.items()
            ],
        }

    @app.get("/unlock")
    def unlock_page():
        if m.UNLOCK_HTML.is_file():
            return HTMLResponse(m.UNLOCK_HTML.read_text(encoding="utf-8"))
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

    def _is_house_secret(key: str) -> bool:
        secret = os.environ.get("OWNER_PROMPT_SECRET", "").strip()
        if not secret or not key:
            return False
        if len(key) != len(secret):
            return False
        return hmac.compare_digest(key, secret)

    @app.post("/recover")
    def recover(body: RecoverIn, response: Response) -> dict:
        key = body.key.strip()
        if not key:
            raise HTTPException(status_code=403, detail="no")
        if _is_house_secret(key):
            raise HTTPException(status_code=403, detail="no")
        buyer_id = buyer_for_recovery_key(key)
        if not buyer_id:
            raise HTTPException(status_code=403, detail="no")
        m._attach_buyer_cookie(response, buyer_id)
        bal = balance(buyer_id)
        recovery_key = ensure_recovery_key(buyer_id)
        return {
            "ok": True,
            "credits": bal["credits"],
            "ltm_pins": bal["ltm_pins"],
            "recovery_key": recovery_key or key,
        }

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
        buyer_id = m._buyer_id(request, response)
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
    def post_prompt(body: m.PromptIn) -> dict:
        check = inspect(body.text)
        mem = m.get_mem()
        if check.verdict == "reject":
            pid = mem.enqueue_prompt(body.text.strip()[:400], status="rejected", reason=check.reason)
            return {"id": pid, "status": "rejected", "reason": check.reason}
        pid = mem.enqueue_prompt(check.text, status="pending")
        return {"id": pid, "status": "pending", "reason": check.reason, "verdict": check.verdict}

    def _stage_html() -> str:
        path = m.STAGE_DIR / "index.html"
        html = path.read_text(encoding="utf-8") if path.is_file() else ""
        tag = '<script src="/stage/private-showing.js"></script>'
        if tag not in html:
            html = html.replace("</body>", tag + "\n</body>", 1) if "</body>" in html else html + tag
        return html

    @app.get("/stage/", include_in_schema=False)
    def stage_slash():
        return HTMLResponse(_stage_html())

    @app.get("/stage/index.html", include_in_schema=False)
    def stage_index_html():
        return HTMLResponse(_stage_html())

    register_episode(app)
