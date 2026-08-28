"""Pre-encode a cheap 640x360 television feed and expose a rolling HLS buffer.

The interactive site remains Godot/WebGL.  This deliberately simpler renderer
turns the same scene packet and Piper WAVs into H.264/AAC once, caches the six
second MPEG-TS fragments in R2, and lets the tiny relay VM stream-copy them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import queue
import random
import shutil
import subprocess
import threading
import time
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from orchestrator import DATA_DIR, ROOT, TTS_DIR
from orchestrator import r2

logger = logging.getLogger(__name__)

BROADCAST_DIR = DATA_DIR / "broadcast"
ASSET_DIR = BROADCAST_DIR / "assets"
WIDTH = 640
HEIGHT = 360
FPS = 30
SEGMENT_SECONDS = 6.0
FALLBACK_ID = "fallback-v2"

_lock = threading.RLock()
_started = False
_job_queue: queue.PriorityQueue = queue.PriorityQueue()
_job_seq = 0
_queued: set[str] = set()
_attempts: dict[str, int] = {}
_assets: dict[str, dict[str, Any]] = {}
_priority_assets: list[str] = []
_schedule: list[dict[str, Any]] = []
_next_sequence = int(time.time() * 1000)
_discontinuity_sequence = 0
_rng = random.Random()
_last_asset = ""
_metrics: dict[str, Any] = {
    "last_error": "",
    "last_render_asset": "",
    "last_render_wall_seconds": 0.0,
    "last_render_media_seconds": 0.0,
    "last_render_speed": 0.0,
    "rendered_assets": 0,
    "failed_assets": 0,
}


@dataclass(frozen=True)
class BeatTiming:
    beat: dict[str, Any]
    start: float
    voice_start: float
    voice_end: float
    end: float


def enabled() -> bool:
    return os.environ.get("BROADCAST_VIDEO_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        value = default
    return max(lo, min(hi, value))


def _float_env(name: str, default: float, lo: float, hi: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
    except ValueError:
        value = default
    return max(lo, min(hi, value))


def ffmpeg_exe() -> str | None:
    configured = os.environ.get("FFMPEG_BIN", "").strip()
    if configured and Path(configured).is_file():
        return configured
    bundled = ROOT / "tools" / "ffmpeg"
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if bundled and Path(bundled).is_file() else None
    except Exception:
        return None


def _packet_id(packet: dict[str, Any]) -> str:
    raw = packet.get("show_episode_id", packet.get("episode_id", "episode"))
    clean = "".join(ch for ch in str(raw) if ch.isalnum() or ch in "-_")[:36] or "episode"
    payload = {
        "scene": packet.get("scene"),
        "topic": packet.get("topic"),
        "beats": [
            {
                key: beat.get(key)
                for key in (
                    "speaker",
                    "line",
                    "emotion",
                    "animation",
                    "target",
                    "camera",
                    "audio",
                    "duration_sec",
                )
            }
            for beat in (packet.get("beats") or [])
            if isinstance(beat, dict)
        ],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:10]
    return f"ep-{clean}-{digest}"


def _hold_for(beat: dict[str, Any], index: int, count: int) -> float:
    anim = str(beat.get("animation") or "")
    emotion = str(beat.get("emotion") or "")
    if index == count - 1:
        return 0.8
    if anim in {"laughing", "happy_dance", "high_five", "victory_pose", "facepalm"}:
        return 0.55
    if emotion in {"shocked", "delighted", "embarrassed"}:
        return 0.5
    return 0.25


def _wav_seconds(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        with wave.open(str(path), "rb") as src:
            rate = src.getframerate()
            return src.getnframes() / float(rate) if rate > 0 else None
    except Exception:
        return None


def _audio_path(beat: dict[str, Any], *, fetch: bool = False) -> Path | None:
    raw = str(beat.get("audio") or beat.get("wav") or "").strip()
    if not raw:
        return None
    name = Path(raw).name
    candidates = (ROOT / raw, TTS_DIR / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if fetch:
        blob = r2.get_bytes(name)
        if blob:
            try:
                TTS_DIR.mkdir(parents=True, exist_ok=True)
                dest = TTS_DIR / name
                dest.write_bytes(blob)
                return dest
            except OSError:
                return None
    return None


def build_timeline(packet: dict[str, Any], *, fetch_audio: bool = False) -> list[BeatTiming]:
    timings: list[BeatTiming] = []
    cursor = 0.0
    beats = [beat for beat in (packet.get("beats") or []) if isinstance(beat, dict)]
    for index, beat in enumerate(beats):
        anim = str(beat.get("animation") or "")
        pre = 0.75 if anim in {"enter", "walking", "sitting"} else 0.0
        wav_len = _wav_seconds(_audio_path(beat, fetch=fetch_audio))
        stated = float(beat.get("duration_sec") or 0.0)
        voice_len = max(0.7, min(12.0, wav_len or stated or max(1.2, len(str(beat.get("line") or "")) / 14.0)))
        start = cursor
        voice_start = start + pre
        voice_end = voice_start + voice_len
        end = voice_end + _hold_for(beat, index, len(beats))
        timings.append(BeatTiming(beat=beat, start=start, voice_start=voice_start, voice_end=voice_end, end=end))
        cursor = end
    return timings


def _write_audio_timeline(
    packet: dict[str, Any],
    timings: list[BeatTiming],
    dest: Path,
    *,
    total_seconds: float | None = None,
) -> None:
    sample_rate = 22050
    total = max(1.0, float(total_seconds or 0.0), timings[-1].end if timings else 12.0)
    pcm = bytearray(int(math.ceil(total * sample_rate)) * 2)
    for timing in timings:
        path = _audio_path(timing.beat, fetch=True)
        if path is None:
            continue
        try:
            with wave.open(str(path), "rb") as src:
                if src.getnchannels() != 1 or src.getsampwidth() != 2 or src.getframerate() != sample_rate:
                    logger.warning("broadcast skipped non-normalized wav %s", path.name)
                    continue
                frames = src.readframes(src.getnframes())
        except Exception:
            continue
        offset = int(round(timing.voice_start * sample_rate)) * 2
        room = max(0, len(pcm) - offset)
        pcm[offset : offset + min(room, len(frames))] = frames[:room]
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm)


@lru_cache(maxsize=32)
def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    names = [
        str(ROOT / "tools" / "DejaVuSans.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default()


def _draw_set(draw, scene: str) -> None:
    palettes = {
        "living_room": ("#c9a766", "#8f4216", "#4a2718"),
        "kitchen": ("#cda85f", "#35634d", "#dccda7"),
        "hallway": ("#ad8354", "#643826", "#b89d73"),
        "porch": ("#31485c", "#79512f", "#182b3a"),
        "front_yard": ("#7fa7c3", "#4c873e", "#59422b"),
    }
    wall, floor, accent = palettes.get(scene, palettes["living_room"])
    draw.rectangle((0, 0, WIDTH, 258), fill=wall)
    draw.rectangle((0, 258, WIDTH, HEIGHT), fill=floor)
    if scene == "kitchen":
        draw.rectangle((55, 126, 570, 250), fill="#416c56", outline="#263f35", width=4)
        draw.rectangle((70, 95, 545, 132), fill="#a85a24")
        for x in (120, 250, 380, 510):
            draw.ellipse((x - 18, 235, x + 18, 270), fill="#dc792b")
    elif scene == "hallway":
        for x in (35, 230, 425):
            draw.rectangle((x, 72, x + 155, 255), fill=accent, outline="#342116", width=6)
        draw.polygon([(0, 258), (WIDTH, 258), (545, HEIGHT), (90, HEIGHT)], fill="#b89d73")
    elif scene == "porch":
        draw.rectangle((45, 55, 300, 258), fill="#7b5535", outline="#34281e", width=6)
        draw.rectangle((410, 95, 560, 258), fill="#132b3a", outline="#9f7c4e", width=7)
        for y in range(278, 360, 22):
            draw.line((0, y, WIDTH, y), fill="#9a7245", width=3)
    elif scene == "front_yard":
        draw.ellipse((475, 28, 560, 113), fill="#f6dc7a")
        draw.rectangle((0, 225, WIDTH, HEIGHT), fill="#4c873e")
        draw.rectangle((35, 125, 255, 270), fill="#a26a3b", outline="#51331f", width=5)
        draw.polygon([(20, 125), (145, 50), (275, 125)], fill="#5e3828")
    else:
        draw.rectangle((120, 188, 520, 295), fill="#a64c15", outline="#6e3212", width=5)
        draw.rectangle((140, 158, 500, 220), fill="#b85d22", outline="#6e3212", width=4)
        draw.rectangle((35, 72, 122, 164), fill="#355566", outline=accent, width=7)
        draw.ellipse((520, 50, 588, 118), fill="#d8bd76", outline="#9c7f42", width=4)


def _positions(scene: str) -> dict[str, tuple[int, int, float]]:
    base = {
        "reed": (145, 283, 1.05),
        "maris": (285, 285, 0.92),
        "jinx": (405, 288, 0.78),
        "quill": (520, 290, 0.74),
    }
    if scene == "kitchen":
        return {"reed": (100, 289, 0.9), "maris": (250, 289, 0.85), "jinx": (400, 291, 0.74), "quill": (535, 292, 0.7)}
    if scene == "hallway":
        return {"reed": (115, 290, 0.92), "maris": (270, 290, 0.85), "jinx": (420, 292, 0.74), "quill": (545, 292, 0.7)}
    return base


def _draw_character(draw, who: str, x: int, ground: int, scale: float, *, active: bool, mouth_open: bool, emotion: str, animation: str, now: float) -> None:
    colors = {"reed": "#315f79", "maris": "#4f8fa2", "jinx": "#269d9a", "quill": "#79b7c3"}
    color = colors.get(who, "#4f8fa2")
    sway = int(math.sin(now * (5.0 if active else 1.8) + len(who)) * (4 if active else 1))
    bounce = int(abs(math.sin(now * 5.5)) * 5) if active and animation in {"laughing", "happy_dance", "celebrate", "victory_pose"} else 0
    x += sway
    ground -= bounce
    head_r = int((31 if who == "reed" else 27 if who == "maris" else 24) * scale)
    body_w = int((58 if who == "reed" else 48) * scale)
    body_h = int((76 if who == "reed" else 66) * scale)
    head_y = ground - body_h - head_r * 2 + 8
    body_top = ground - body_h
    draw.rounded_rectangle((x - body_w // 2, body_top, x + body_w // 2, ground), radius=max(8, body_w // 3), fill=color, outline="#163544", width=2)
    draw.ellipse((x - head_r, head_y, x + head_r, head_y + head_r * 2), fill=color, outline="#163544", width=2)
    eye_y = head_y + int(head_r * 0.72)
    eye_dx = max(8, int(head_r * 0.42))
    if emotion in {"laughing", "delighted", "playful"}:
        draw.arc((x - eye_dx - 5, eye_y - 1, x - eye_dx + 5, eye_y + 8), 190, 350, fill="#10222d", width=2)
        draw.arc((x + eye_dx - 5, eye_y - 1, x + eye_dx + 5, eye_y + 8), 190, 350, fill="#10222d", width=2)
    else:
        draw.ellipse((x - eye_dx - 4, eye_y, x - eye_dx + 4, eye_y + 9), fill="#f5e6b5")
        draw.ellipse((x + eye_dx - 4, eye_y, x + eye_dx + 4, eye_y + 9), fill="#f5e6b5")
        draw.ellipse((x - eye_dx - 1, eye_y + 3, x - eye_dx + 2, eye_y + 7), fill="#13232b")
        draw.ellipse((x + eye_dx - 1, eye_y + 3, x + eye_dx + 2, eye_y + 7), fill="#13232b")
    mouth_y = head_y + int(head_r * 1.38)
    if mouth_open:
        draw.ellipse((x - 8, mouth_y - 2, x + 8, mouth_y + 10), fill="#291419")
    elif emotion in {"happy", "delighted", "laughing", "playful", "proud"}:
        draw.arc((x - 10, mouth_y - 5, x + 10, mouth_y + 8), 10, 170, fill="#28151a", width=2)
    else:
        draw.line((x - 7, mouth_y + 4, x + 7, mouth_y + 4), fill="#28151a", width=2)
    shoulder_y = body_top + 18
    arm = int(34 * scale)
    if animation in {"pointing", "high_five", "victory_pose"} and active:
        draw.line((x + body_w // 2 - 2, shoulder_y, x + body_w // 2 + arm, shoulder_y - 18), fill=color, width=max(5, int(8 * scale)))
    elif animation == "arms_crossed":
        draw.line((x - body_w // 2, shoulder_y, x + body_w // 3, shoulder_y + 28), fill=color, width=max(5, int(8 * scale)))
        draw.line((x + body_w // 2, shoulder_y, x - body_w // 3, shoulder_y + 28), fill=color, width=max(5, int(8 * scale)))
    else:
        draw.line((x - body_w // 2 + 2, shoulder_y, x - body_w // 2 - 8, shoulder_y + arm), fill=color, width=max(5, int(8 * scale)))
        draw.line((x + body_w // 2 - 2, shoulder_y, x + body_w // 2 + 8, shoulder_y + arm), fill=color, width=max(5, int(8 * scale)))
    if who == "quill":
        draw.rectangle((x - eye_dx - 7, eye_y - 3, x - 2, eye_y + 13), outline="#17232a", width=2)
        draw.rectangle((x + 2, eye_y - 3, x + eye_dx + 7, eye_y + 13), outline="#17232a", width=2)
        draw.line((x - 2, eye_y + 3, x + 2, eye_y + 3), fill="#17232a", width=2)


def _wrap(text: str, width: int = 62) -> list[str]:
    words = str(text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2]


def _frame(packet: dict[str, Any], timings: list[BeatTiming], now: float):
    from PIL import Image, ImageDraw

    scene = str(packet.get("scene") or "living_room")
    image = Image.new("RGB", (WIDTH, HEIGHT), "#111821")
    draw = ImageDraw.Draw(image)
    _draw_set(draw, scene)
    current = timings[-1] if timings else None
    for timing in timings:
        if timing.start <= now < timing.end:
            current = timing
            break
    beat = current.beat if current else {}
    speaker = str(beat.get("speaker") or "")
    positions = _positions(scene)
    for who in ("reed", "maris", "jinx", "quill"):
        x, ground, scale = positions[who]
        active = who == speaker and current is not None and current.voice_start <= now < current.voice_end
        mouth_open = active and int((now - current.voice_start) * 11) % 2 == 0
        _draw_character(
            draw,
            who,
            x,
            ground,
            scale,
            active=active,
            mouth_open=mouth_open,
            emotion=str(beat.get("emotion") or "calm") if who == speaker else "calm",
            animation=str(beat.get("animation") or "idle") if who == speaker else "idle",
            now=now,
        )
    camera = str(beat.get("camera") or "auto")
    if speaker in positions and camera in {"medium", "dramatic_closeup", "reaction"}:
        cx = positions[speaker][0]
        crop_w = 500 if camera == "medium" else 430
        left = max(0, min(WIDTH - crop_w, cx - crop_w // 2))
        image = image.crop((left, 30, left + crop_w, 330)).resize((WIDTH, HEIGHT))
        draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 42), fill="#101722")
    draw.ellipse((14, 14, 24, 24), fill="#f05a4f")
    draw.text((31, 10), "THE SINGULARITY BLUES", font=_font(17, bold=True), fill="#eef3f6")
    topic = str(packet.get("topic") or "")[:54]
    draw.text((315, 11), topic, font=_font(13), fill="#e4c98d")
    draw.rounded_rectangle((20, 286, 620, 350), radius=10, fill="#0b111b", outline="#4d8fb0", width=2)
    if beat:
        draw.text((34, 294), speaker.upper(), font=_font(11, bold=True), fill="#83c7e5")
        for line_no, line in enumerate(_wrap(str(beat.get("line") or ""))):
            draw.text((34, 310 + line_no * 16), line, font=_font(14), fill="#f7f1e8")
    return image


def _parse_hls_manifest(path: Path) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    duration: float | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            try:
                duration = float(line.split(":", 1)[1].split(",", 1)[0])
            except ValueError:
                duration = SEGMENT_SECONDS
        elif line and not line.startswith("#") and duration is not None:
            segments.append({"name": Path(line).name, "duration": duration})
            duration = None
    return segments


def render_asset(packet: dict[str, Any], asset_id: str | None = None) -> dict[str, Any]:
    """Render one packet once. Called only by the background worker."""
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is unavailable")
    from PIL import Image  # noqa: F401 - fail early before making partial assets

    asset_id = asset_id or _packet_id(packet)
    final_dir = ASSET_DIR / asset_id
    tmp_dir = ASSET_DIR / f".{asset_id}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    timings = build_timeline(packet, fetch_audio=True)
    media_seconds = max(12.0, timings[-1].end if timings else 12.0)
    audio = tmp_dir / "audio.wav"
    _write_audio_timeline(packet, timings, audio, total_seconds=media_seconds)
    output = tmp_dir / "index.m3u8"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-video_size",
        f"{WIDTH}x{HEIGHT}",
        "-framerate",
        str(FPS),
        "-i",
        "pipe:0",
        "-i",
        str(audio),
        "-c:v",
        "libx264",
        "-preset",
        os.environ.get("BROADCAST_X264_PRESET", "ultrafast"),
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-g",
        str(FPS * 2),
        "-keyint_min",
        str(FPS * 2),
        "-sc_threshold",
        "0",
        "-b:v",
        os.environ.get("BROADCAST_VIDEO_BITRATE", "900k"),
        "-maxrate",
        os.environ.get("BROADCAST_VIDEO_MAXRATE", "1200k"),
        "-bufsize",
        os.environ.get("BROADCAST_VIDEO_BUFSIZE", "1800k"),
        "-threads",
        str(_int_env("BROADCAST_ENCODER_THREADS", 2, 1, 2)),
        "-c:a",
        "aac",
        "-b:a",
        os.environ.get("BROADCAST_AUDIO_BITRATE", "96k"),
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        "-f",
        "hls",
        "-hls_time",
        str(SEGMENT_SECONDS),
        "-hls_list_size",
        "0",
        "-hls_segment_type",
        "mpegts",
        "-hls_flags",
        "independent_segments+temp_file",
        "-hls_segment_filename",
        str(tmp_dir / "seg-%03d.ts"),
        str(output),
    ]
    nice = shutil.which("nice")
    if nice:
        command = [nice, "-n", str(_int_env("BROADCAST_ENCODER_NICE", 10, 0, 19)), *command]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    frames = int(math.ceil(media_seconds * FPS))
    speed_limit = _float_env("BROADCAST_RENDER_SPEED_LIMIT", 0.0, 0.0, 30.0)
    frame_started = time.monotonic()
    broken = False
    try:
        assert proc.stdin is not None
        for frame_no in range(frames):
            image = _frame(packet, timings, frame_no / float(FPS))
            proc.stdin.write(image.tobytes())
            if speed_limit > 0:
                due = (frame_no + 1) / float(FPS) / speed_limit
                pause = due - (time.monotonic() - frame_started)
                if pause > 0:
                    time.sleep(pause)
    except BrokenPipeError:
        broken = True
    finally:
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    code = proc.wait(timeout=max(60, int(media_seconds * 2)))
    if broken or code != 0 or not output.is_file():
        raise RuntimeError(f"broadcast ffmpeg failed ({code}): {stderr[-800:]}")
    segments = _parse_hls_manifest(output)
    if not segments:
        raise RuntimeError("broadcast encoder produced no HLS segments")
    manifest = {
        "version": 1,
        "asset_id": asset_id,
        "episode_id": packet.get("show_episode_id", packet.get("episode_id")),
        "topic": str(packet.get("topic") or ""),
        "scene": str(packet.get("scene") or "living_room"),
        "duration": round(sum(float(item["duration"]) for item in segments), 3),
        "segments": segments,
        "remote": False,
        "rendered_at": time.time(),
    }
    (tmp_dir / "asset.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)
    tmp_dir.replace(final_dir)
    remote = False
    if r2.configured():
        remote = all(
            r2.put_object_file(final_dir / item["name"], f"broadcast/{asset_id}/{item['name']}")
            for item in segments
        )
        if remote:
            manifest["remote"] = True
            (final_dir / "asset.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            remote = r2.put_object_file(final_dir / "asset.json", f"broadcast/{asset_id}/asset.json")
            manifest["remote"] = bool(remote)
    return manifest


def _load_manifest(asset_id: str) -> dict[str, Any] | None:
    local = ASSET_DIR / asset_id / "asset.json"
    if local.is_file():
        try:
            manifest = json.loads(local.read_text(encoding="utf-8"))
            if manifest.get("segments"):
                return manifest
        except Exception:
            pass
    if r2.configured():
        blob = r2.get_object_bytes(f"broadcast/{asset_id}/asset.json")
        if blob:
            try:
                manifest = json.loads(blob.decode("utf-8"))
                if manifest.get("segments"):
                    manifest["remote"] = True
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                    return manifest
            except Exception:
                pass
    return None


def enqueue(packet: dict[str, Any], *, priority: int = 10) -> str | None:
    if not enabled() or not isinstance(packet, dict) or not packet.get("beats"):
        return None
    asset_id = FALLBACK_ID if packet.get("broadcast_fallback") else _packet_id(packet)
    global _job_seq
    with _lock:
        if asset_id in _assets or asset_id in _queued:
            return asset_id
        _job_seq += 1
        _queued.add(asset_id)
        _job_queue.put((int(priority), _job_seq, asset_id, json.loads(json.dumps(packet))))
    return asset_id


def _fallback_packet() -> dict[str, Any]:
    return {
        "episode_id": "fallback",
        "scene": "living_room",
        "topic": "The signal is regrouping",
        "source": "fallback",
        "broadcast_fallback": True,
        "beats": [
            {
                "speaker": "maris",
                "line": "The Singularity Blues will return after this extremely inexpensive technical pause.",
                "emotion": "calm",
                "animation": "arms_crossed",
                "camera": "medium",
                "duration_sec": 12.0,
            }
        ],
    }


def sync_now() -> int:
    try:
        from orchestrator.playlist import broadcast_packets

        packets = broadcast_packets()
    except Exception:
        packets = []
    for packet in packets:
        enqueue(packet, priority=20)
    return len(packets)


def _register(manifest: dict[str, Any], *, priority: bool = False) -> None:
    asset_id = str(manifest.get("asset_id") or "")
    if not asset_id:
        return
    with _lock:
        _assets[asset_id] = manifest
        if priority and asset_id != FALLBACK_ID and asset_id not in _priority_assets:
            _priority_assets.append(asset_id)


def _worker() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    enqueue(_fallback_packet(), priority=-100)
    last_sync = 0.0
    while True:
        if time.time() - last_sync > 10.0:
            sync_now()
            last_sync = time.time()
        try:
            priority, _seq, asset_id, packet = _job_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        started = time.monotonic()
        try:
            manifest = _load_manifest(asset_id)
            if manifest is None:
                logger.info("broadcast rendering %s", asset_id)
                manifest = render_asset(packet, asset_id)
            wall = max(0.001, time.monotonic() - started)
            media = float(manifest.get("duration") or 0.0)
            _register(manifest, priority=priority <= 0)
            with _lock:
                _metrics.update(
                    {
                        "last_error": "",
                        "last_render_asset": asset_id,
                        "last_render_wall_seconds": round(wall, 3),
                        "last_render_media_seconds": round(media, 3),
                        "last_render_speed": round(media / wall, 2),
                        "rendered_assets": int(_metrics["rendered_assets"]) + 1,
                    }
                )
                _attempts.pop(asset_id, None)
            logger.info("broadcast ready %s %.1fs media in %.1fs (%.1fx)", asset_id, media, wall, media / wall)
            _cleanup_disk()
            time.sleep(_float_env("BROADCAST_RENDER_COOLDOWN_SEC", 1.0, 0.0, 30.0))
        except Exception as exc:
            logger.exception("broadcast render failed for %s", asset_id)
            with _lock:
                _metrics["last_error"] = f"{type(exc).__name__}: {exc}"[:300]
                _metrics["failed_assets"] = int(_metrics["failed_assets"]) + 1
                _attempts[asset_id] = _attempts.get(asset_id, 0) + 1
                attempt = _attempts[asset_id]
            if attempt < 3:
                time.sleep(min(30.0, 3.0 * attempt))
                with _lock:
                    global _job_seq
                    _job_seq += 1
                    _job_queue.put((priority + attempt, _job_seq, asset_id, packet))
                    continue
        finally:
            with _lock:
                if _attempts.get(asset_id, 0) >= 3 or asset_id in _assets:
                    _queued.discard(asset_id)
            _job_queue.task_done()


def _choose_asset() -> dict[str, Any] | None:
    global _last_asset
    with _lock:
        while _priority_assets:
            asset_id = _priority_assets.pop(0)
            manifest = _assets.get(asset_id)
            if manifest:
                _last_asset = asset_id
                return manifest
        real = [manifest for key, manifest in _assets.items() if key != FALLBACK_ID]
        pool = [m for m in real if str(m.get("asset_id")) != _last_asset] or real
        if pool:
            chosen = _rng.choice(pool)
            _last_asset = str(chosen.get("asset_id") or "")
            return chosen
        return _assets.get(FALLBACK_ID)


def _ensure_buffer(now: float | None = None) -> None:
    global _next_sequence, _discontinuity_sequence
    now = time.time() if now is None else now
    target = _float_env("BROADCAST_BUFFER_SECONDS", 60.0, 30.0, 180.0)
    window = _float_env("BROADCAST_WINDOW_SECONDS", 30.0, 12.0, 120.0)
    with _lock:
        retained = [item for item in _schedule if float(item["end"]) >= now - window]
        removed = _schedule[: len(_schedule) - len(retained)]
        _discontinuity_sequence += sum(1 for item in removed if item.get("discontinuity"))
        _schedule[:] = retained
        end = max((float(item["end"]) for item in _schedule), default=now)
    guard = 0
    while end < now + target and guard < 100:
        guard += 1
        manifest = _choose_asset()
        if manifest is None:
            return
        asset_id = str(manifest.get("asset_id") or "")
        pieces = manifest.get("segments") or []
        if not asset_id or not pieces:
            return
        additions = []
        for index, piece in enumerate(pieces):
            duration = max(0.1, float(piece.get("duration") or SEGMENT_SECONDS))
            additions.append(
                {
                    "sequence": _next_sequence,
                    "asset_id": asset_id,
                    "name": Path(str(piece.get("name") or "")).name,
                    "duration": duration,
                    "start": end,
                    "end": end + duration,
                    "discontinuity": index == 0,
                    "remote": bool(manifest.get("remote")),
                }
            )
            _next_sequence += 1
            end += duration
        with _lock:
            _schedule.extend(additions)


def _scheduler() -> None:
    while True:
        try:
            _ensure_buffer()
        except Exception:
            logger.exception("broadcast scheduler failed")
        time.sleep(1.0)


def start() -> bool:
    global _started
    if not enabled():
        return False
    with _lock:
        if _started:
            return True
        _started = True
    threading.Thread(target=_worker, daemon=True, name="broadcast-render").start()
    threading.Thread(target=_scheduler, daemon=True, name="broadcast-scheduler").start()
    return True


def _segment_url(item: dict[str, Any]) -> str:
    asset_id = quote(str(item["asset_id"]), safe="-_~")
    name = quote(Path(str(item["name"])).name, safe="-_.~")
    base = os.environ.get("R2_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base and item.get("remote"):
        return f"{base}/broadcast/{asset_id}/{name}?seq={item['sequence']}"
    return f"/broadcast/segments/{asset_id}/{name}?seq={item['sequence']}"


def live_manifest() -> str:
    _ensure_buffer()
    with _lock:
        items = list(_schedule)
    if not items:
        raise RuntimeError("broadcast buffer is warming")
    target = int(math.ceil(max(float(item["duration"]) for item in items)))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{max(1, target)}",
        f"#EXT-X-MEDIA-SEQUENCE:{items[0]['sequence']}",
        f"#EXT-X-DISCONTINUITY-SEQUENCE:{_discontinuity_sequence}",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    for item in items:
        if item.get("discontinuity"):
            lines.append("#EXT-X-DISCONTINUITY")
        lines.append(f"#EXTINF:{float(item['duration']):.3f},")
        lines.append(_segment_url(item))
    return "\n".join(lines) + "\n"


def segment_file(asset_id: str, filename: str) -> Path | None:
    safe_id = "".join(ch for ch in str(asset_id) if ch.isalnum() or ch in "-_")
    safe_name = Path(filename).name
    if safe_id != asset_id or safe_name != filename or not safe_name.endswith(".ts"):
        return None
    path = ASSET_DIR / safe_id / safe_name
    if path.is_file():
        try:
            os.utime(path.parent, None)
        except OSError:
            pass
        return path
    blob = r2.get_object_bytes(f"broadcast/{safe_id}/{safe_name}")
    if not blob:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        return path
    except OSError:
        return None


def _cleanup_disk() -> None:
    limit = _int_env("BROADCAST_MAX_DISK_MB", 384, 64, 2048) * 1024 * 1024
    if not ASSET_DIR.is_dir():
        return
    dirs = [path for path in ASSET_DIR.iterdir() if path.is_dir() and not path.name.startswith(".")]
    sizes = []
    for path in dirs:
        size = sum(item.stat().st_size for item in path.glob("**/*") if item.is_file())
        sizes.append((path.stat().st_mtime, path, size))
    total = sum(item[2] for item in sizes)
    with _lock:
        protected = {str(item.get("asset_id") or "") for item in _schedule}
    for _mtime, path, size in sorted(sizes):
        if total <= limit:
            break
        if path.name in protected or path.name == FALLBACK_ID:
            continue
        shutil.rmtree(path, ignore_errors=True)
        total -= size
        with _lock:
            manifest = _assets.get(path.name) or {}
            if not manifest.get("remote"):
                _assets.pop(path.name, None)


def health() -> dict[str, Any]:
    now = time.time()
    try:
        load_average = [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load_average = []
    try:
        pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
        process_rss_mb = round(pages * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024, 2)
    except (OSError, ValueError, IndexError):
        process_rss_mb = None
    with _lock:
        buffered = max((float(item["end"]) for item in _schedule), default=now) - now
        metrics = dict(_metrics)
        assets = len(_assets)
        scheduled = len(_schedule)
        queued = _job_queue.qsize()
    return {
        "enabled": enabled(),
        "started": _started,
        "ffmpeg": bool(ffmpeg_exe()),
        "video": {"codec": "h264", "width": WIDTH, "height": HEIGHT, "fps": FPS},
        "audio": {"codec": "aac", "sample_rate": 48000, "channels": 2},
        "segment_seconds": SEGMENT_SECONDS,
        "load_average": load_average,
        "process_rss_mb": process_rss_mb,
        "webgl_context_losses": 0,
        "r2": r2.configured(),
        "r2_public": bool(os.environ.get("R2_PUBLIC_BASE_URL", "").strip()),
        "assets": assets,
        "queued_assets": queued,
        "scheduled_segments": scheduled,
        "buffered_seconds": round(max(0.0, buffered), 2),
        **metrics,
    }
