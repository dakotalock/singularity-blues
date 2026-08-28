import random
import sys
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import broadcast
from tools import fetch_ffmpeg
from web.app import app


def _packet(line="A very inexpensive joke."):
    return {
        "episode_id": 42,
        "scene": "kitchen",
        "topic": "Potato television",
        "beats": [
            {
                "speaker": "reed",
                "line": line,
                "emotion": "delighted",
                "animation": "laughing",
                "duration_sec": 1.0,
            }
        ],
    }


def test_broadcast_is_opt_in(monkeypatch):
    monkeypatch.delenv("BROADCAST_VIDEO_ENABLED", raising=False)
    assert broadcast.enabled() is False
    health = broadcast.health()
    assert health["video"] == {"codec": "h264", "width": 640, "height": 360, "fps": 30}
    assert health["audio"]["codec"] == "aac"
    assert health["webgl_context_losses"] == 0
    monkeypatch.setenv("BROADCAST_VIDEO_ENABLED", "1")
    assert broadcast.enabled() is True


def test_asset_id_is_content_addressed():
    first = broadcast._packet_id(_packet("first"))
    assert first == broadcast._packet_id(_packet("first"))
    assert first != broadcast._packet_id(_packet("second"))


def test_timeline_is_monotonic_and_frame_draws():
    packet = _packet()
    timings = broadcast.build_timeline(packet)
    assert timings and timings[0].start == 0
    assert timings[0].start <= timings[0].voice_start < timings[0].voice_end <= timings[0].end
    frame = broadcast._frame(packet, timings, 0.5)
    assert frame.size == (640, 360)
    assert frame.mode == "RGB"


def test_live_manifest_is_rolling_and_stream_copy_compatible(monkeypatch):
    manifest = {
        "asset_id": "ep-42-deadbeef",
        "remote": False,
        "duration": 12.0,
        "segments": [
            {"name": "seg-000.ts", "duration": 6.0},
            {"name": "seg-001.ts", "duration": 6.0},
        ],
    }
    monkeypatch.setattr(broadcast, "_assets", {manifest["asset_id"]: manifest})
    monkeypatch.setattr(broadcast, "_priority_assets", [])
    monkeypatch.setattr(broadcast, "_schedule", [])
    monkeypatch.setattr(broadcast, "_last_asset", "")
    monkeypatch.setattr(broadcast, "_next_sequence", 123)
    monkeypatch.setattr(broadcast, "_discontinuity_sequence", 0)
    monkeypatch.setattr(broadcast, "_rng", random.Random(1))
    monkeypatch.setattr(broadcast.time, "time", lambda: 1_000.0)
    monkeypatch.setenv("BROADCAST_BUFFER_SECONDS", "30")
    monkeypatch.delenv("R2_PUBLIC_BASE_URL", raising=False)

    broadcast._ensure_buffer(now=1_000.0)
    text = broadcast.live_manifest()
    assert "#EXTM3U" in text
    assert "#EXT-X-MEDIA-SEQUENCE:123" in text
    assert "#EXT-X-DISCONTINUITY-SEQUENCE:0" in text
    assert "#EXT-X-INDEPENDENT-SEGMENTS" in text
    assert "#EXT-X-DISCONTINUITY" in text
    assert "/broadcast/segments/ep-42-deadbeef/seg-000.ts?seq=123" in text


def test_relay_normal_path_is_packet_copy_without_browser():
    root = Path(__file__).parents[1]
    script = (root / "tools" / "livestream" / "relay.sh").read_text(encoding="utf-8")
    assert "-c:v copy -c:a copy" in script
    for forbidden in ("chromium", "x11grab", "Xvfb", "minterpolate", "-vf scale"):
        assert forbidden not in script

    unit = (root / "tools" / "livestream" / "singularity-blues-relay.service").read_text(encoding="utf-8")
    assert "Restart=always" in unit
    assert "RestartSec=15" in unit


def test_broadcast_http_routes(monkeypatch, tmp_path):
    monkeypatch.setattr(broadcast, "start", lambda: True)
    monkeypatch.setattr(
        broadcast,
        "live_manifest",
        lambda: "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.000,\nsegment.ts\n",
    )
    segment = tmp_path / "seg-000.ts"
    segment.write_bytes(b"mpeg-ts-packet")
    monkeypatch.setattr(broadcast, "segment_file", lambda asset_id, filename: segment)
    client = TestClient(app)

    manifest = client.get("/broadcast/live.m3u8")
    assert manifest.status_code == 200
    assert manifest.headers["cache-control"].startswith("no-store")
    assert manifest.headers["content-type"].startswith("application/vnd.apple.mpegurl")

    media = client.get("/broadcast/segments/ep-1/seg-000.ts")
    assert media.status_code == 200
    assert media.headers["content-type"] == "video/mp2t"
    assert media.headers["cache-control"].endswith("immutable")


def test_render_ffmpeg_fetch_has_installed_wheel_fallback(monkeypatch, tmp_path):
    bundled = tmp_path / "wheel-ffmpeg"
    bundled.write_bytes(b"fake-ffmpeg")
    bundled.chmod(0o755)
    destination = tmp_path / "tools" / "ffmpeg"
    monkeypatch.setattr(fetch_ffmpeg, "DEST", destination)
    monkeypatch.setattr(fetch_ffmpeg, "_download", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setitem(
        sys.modules,
        "imageio_ffmpeg",
        SimpleNamespace(get_ffmpeg_exe=lambda: str(bundled)),
    )

    fetch_ffmpeg._ensure_ffmpeg()
    assert destination.read_bytes() == b"fake-ffmpeg"
    assert destination.stat().st_mode & 0o111
