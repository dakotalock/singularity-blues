"""Serve pre-encoded TV segments. The VPS ffmpeg -c copies these to Twitch/YouTube."""

from __future__ import annotations

import json
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from orchestrator import DATA_DIR
from orchestrator import tv as tvpack

BROADCAST_DIR = DATA_DIR / "broadcast"


def register(app):
    @app.get("/broadcast/live.m3u8")
    def live_playlist():
        path = BROADCAST_DIR / "live.m3u8"
        if not path.is_file():
            try:
                tvpack.write_live_playlist()
            except Exception:
                pass
        if not path.is_file():
            raise HTTPException(status_code=503, detail="broadcast not ready")
        return PlainTextResponse(
            path.read_text(encoding="utf-8"),
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/broadcast/window.json")
    def window():
        path = BROADCAST_DIR / "window.json"
        if not path.is_file():
            try:
                tvpack.write_live_playlist()
            except Exception:
                pass
        if not path.is_file():
            return JSONResponse({"segments": [], "queue_seconds": 0, "ffmpeg": bool(tvpack.ffmpeg_bin())})
        return JSONResponse(
            {**tvpack.status(), **json.loads(path.read_text())},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/broadcast/status.json")
    def broadcast_status():
        return tvpack.status()

    @app.get("/broadcast/hold.ts")
    def hold():
        path = tvpack.ensure_hold()
        return FileResponse(path, media_type="video/mp2t", headers={"Cache-Control": "public, max-age=60"})

    @app.get("/broadcast/seg/{name}")
    def segment(name: str):
        safe = name.replace("/", "").replace("..", "")
        if not safe.endswith(".ts"):
            raise HTTPException(status_code=404, detail="no")
        path = BROADCAST_DIR / "seg" / safe
        if not path.is_file():
            raise HTTPException(status_code=404, detail="no")
        return FileResponse(path, media_type="video/mp2t", headers={"Cache-Control": "public, max-age=120"})
