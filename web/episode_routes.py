"""Episode, queue, and stage static routes."""

import json
import uuid
from pathlib import Path

from fastapi import Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from orchestrator.credits import (
    balance,
    refund_credit,
    refund_pin,
    spend_credit,
    spend_pin,
    stripe_configured,
)
from orchestrator.gemini import PromptRefused
from orchestrator.moderation import episode_title, inspect, sanitize_display_name
from orchestrator.playlist import board as playlist_board
from orchestrator.playlist import current as playlist_current
from orchestrator.playlist import snapshot as playlist_snapshot
from orchestrator import r2
from orchestrator.writer_cascade import DEFAULT_VETO_NOTE


def register_episode(app):
    import web.app as m

    @app.post("/episode")
    async def post_episode(
        request: Request,
        response: Response,
        body: m.EpisodeIn | None = None,
        x_owner_secret: str | None = Header(default=None),
    ) -> dict:
        """Start an episode in the background. Poll GET /episode/status."""
        if not m.has_gemini_key():
            raise HTTPException(status_code=503, detail="Writer is not configured")
        owner = m._is_owner(request, x_owner_secret)
        buyer_id = m._buyer_id(request, response)
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

        refuse_reason = check.reason if check.verdict == "refuse" else None
        writer_topic = check.text
        title = episode_title(writer_topic, username, refuse_reason=refuse_reason)
        private = bool(body and body.private_showing)
        job_id = uuid.uuid4().hex[:12]
        with m._jobs_lock:
            m._jobs[job_id] = {
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
                "note": "",
                "refunded": False,
                "credits": balance(buyer_id)["credits"],
                "private": private,
            }
            if not private:
                m._job_order.append(job_id)
            m._latest_job = job_id
        eta = m._eta_for_job(job_id)

        def _progress(update: dict) -> None:
            with m._jobs_lock:
                job = m._jobs.get(job_id)
                if not job:
                    return
                for key in ("phase", "beat", "beats", "speaker"):
                    if key in update:
                        job[key] = update[key]

        def _work() -> None:
            try:
                _progress({"phase": "writing"})
                kwargs = dict(
                    topic=writer_topic,
                    once=False,
                    progress=_progress,
                    username=username,
                    paid=paid,
                    refuse_reason=refuse_reason,
                    ltm_pin=want_pin,
                    title=title,
                    air=not private,
                )
                if private:
                    packet = m.run_episode(m.get_mem(), **kwargs)
                else:
                    with m._episode_lock:
                        packet = m.run_episode(m.get_mem(), **kwargs)
                with m._jobs_lock:
                    job = m._jobs[job_id]
                    job["status"] = "ready"
                    job["phase"] = "ready"
                    job["episode_id"] = packet.get("episode_id")
                    job["topic"] = packet.get("topic") or job.get("topic") or ""
                    job["beats"] = len(packet.get("beats") or [])
                    job["beat"] = job["beats"]
                    job["private"] = private
                    if private:
                        job["packet"] = m._viewer_private_packet(packet)
            except PromptRefused as exc:
                if spent:
                    refund_credit(buyer_id, 1)
                if pin_spent:
                    refund_pin(buyer_id, 1)
                note = m._safe_refuse_note(exc.note) or DEFAULT_VETO_NOTE
                error = (
                    "The topic was moderated by the AI. Your prompt credit was restored."
                    if spent
                    else DEFAULT_VETO_NOTE
                )
                with m._jobs_lock:
                    job = m._jobs[job_id]
                    job["status"] = "refused"
                    job["phase"] = "refused"
                    job["note"] = note
                    job["error"] = error
                    job["refunded"] = True
                    job["credits"] = balance(buyer_id)["credits"]
            except Exception as exc:
                if spent:
                    refund_credit(buyer_id, 1)
                if pin_spent:
                    refund_pin(buyer_id, 1)
                with m._jobs_lock:
                    job = m._jobs[job_id]
                    job["status"] = "error"
                    job["phase"] = "error"
                    job["error"] = m._public_job_error(exc)
                    job["refunded"] = True
                    job["credits"] = balance(buyer_id)["credits"]

        m._spawn_job(_work, concurrent=private)
        return {
            "job_id": job_id,
            "status": "started",
            "topic": title,
            "username": username,
            "paid": paid,
            "credits": balance(buyer_id)["credits"],
            "private": private,
            **eta,
        }

    @app.get("/episode/status")
    def episode_status(job_id: str | None = None) -> dict:
        jid = job_id or m._latest_job
        if not jid:
            rem = m.remaining_seconds()
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
                "eta_copy": (f"Now: {topic}" if (topic := m._airing_topic()) else ""),
            }
        snap = m._job_snapshot(jid)
        if not snap:
            raise HTTPException(status_code=404, detail="unknown job")
        return snap

    @app.get("/queue")
    def queue_board() -> dict:
        """Public now-playing + upcoming written episodes. Writing jobs are listed separately."""
        board = playlist_board()
        writing: list[dict] = []
        with m._jobs_lock:
            for jid in m._job_order:
                job = m._jobs.get(jid) or {}
                if job.get("private"):
                    continue
                if job.get("status") in ("error", "rejected", "refused", "ready"):
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
        if m.NOW_PLAYING_PATH.is_file():
            return json.loads(m.NOW_PLAYING_PATH.read_text(encoding="utf-8"))
        return {"episode_id": None, "scene": None, "topic": None, "beats": []}

    @app.get("/characters")
    def characters() -> dict:
        return {"characters": m.get_mem().list_characters()}

    @app.get("/memories")
    def memories() -> dict:
        return {"memories": m.get_mem().list_memories(limit=50)}

    @app.get("/data/tts/{filename}")
    def tts_wav(filename: str):
        name = Path(filename).name
        if not name or name == "..":
            raise HTTPException(status_code=400, detail="bad filename")
        path = m.TTS_DIR / name
        if path.is_file():
            return FileResponse(path, media_type="audio/wav", filename=name)
        blob = r2.get_bytes(name)
        if not blob:
            raise HTTPException(status_code=404, detail="wav missing")
        try:
            m.TTS_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            return FileResponse(path, media_type="audio/wav", filename=name)
        except Exception:
            return Response(content=blob, media_type="audio/wav")

    @app.get("/stage/index.wasm")
    def stage_wasm():
        path = m.STAGE_DIR / "index.wasm"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="stage wasm missing")
        return FileResponse(path, media_type="application/wasm")

    @app.get("/playlist")
    def playlist() -> dict:
        return playlist_snapshot()

    @app.get("/history")
    def history() -> dict:
        return {"episodes": m.get_mem().list_episodes(limit=30)}

    if m.STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(m.STATIC_DIR)), name="static")
    if m.STAGE_DIR.is_dir() and (m.STAGE_DIR / "index.html").is_file():
        app.mount("/stage", StaticFiles(directory=str(m.STAGE_DIR), html=True), name="stage")
