"""HLS endpoints for the pre-encoded low-cost broadcast feed."""

from pathlib import Path

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from orchestrator import broadcast


def register_broadcast(app) -> None:
    @app.get("/broadcast/live.m3u8", include_in_schema=False)
    def broadcast_manifest() -> Response:
        broadcast.start()
        try:
            manifest = broadcast.live_manifest()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(
            manifest,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.get("/broadcast/segments/{asset_id}/{filename}", include_in_schema=False)
    def broadcast_segment(asset_id: str, filename: str):
        path = broadcast.segment_file(asset_id, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="broadcast segment missing")
        return FileResponse(
            Path(path),
            media_type="video/mp2t",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.get("/broadcast/healthz", include_in_schema=False)
    @app.get("/broadcast/status.json", include_in_schema=False)
    def broadcast_health() -> dict:
        return broadcast.health()

    @app.get("/broadcast/window.json", include_in_schema=False)
    def broadcast_window() -> JSONResponse:
        # Compatibility for the first TV-packager implementation that briefly
        # shipped on main. New monitoring should use /broadcast/healthz.
        health = broadcast.health()
        return JSONResponse(
            {
                **health,
                "queue_seconds": health.get("buffered_seconds", 0),
                "segments": health.get("scheduled_segments", 0),
            },
            headers={"Cache-Control": "no-store"},
        )


# Compatibility with the earlier module API on current GitHub.
register = register_broadcast
