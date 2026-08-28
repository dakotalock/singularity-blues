"""Cheap TV-camera packager: still cards + Piper wavs -> H.264/AAC MPEG-TS.

Website Godot stays as-is. Livestream is a separate 720p representation of the
same playlist clock: one 5-30s segment per beat, about 90s queued ahead. The
$5 VPS only ffmpeg -c copy those segments to RTMP.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Any

from orchestrator import DATA_DIR, ROOT, TTS_DIR

BROADCAST_DIR = DATA_DIR / "broadcast"
SEG_DIR = BROADCAST_DIR / "seg"
HOLD_NAME = "hold.ts"
LIVE_NAME = "live.m3u8"
WINDOW_NAME = "window.json"
SEG_MIN = 5.0
SEG_MAX = 30.0
LOOKAHEAD_SEC = 90.0
HOLD_SEC = 6.0
WIDTH = 1280
HEIGHT = 720
FPS = 30
AAC_HZ = 44100
PACKAGER_SLEEP = 2.0
FONTS = (
    ROOT / "tools" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)

CAST = (
    ("reed", "Reed", "0x3D6EA8"),
    ("maris", "Maris", "0x5B8FC7"),
    ("jinx", "Jinx", "0x7EC8E3"),
    ("quill", "Quill", "0xA8D4F0"),
)

_lock = threading.RLock()
_started = threading.Event()
_encode_lock = threading.Lock()


def ffmpeg_bin() -> str | None:
    bundled = ROOT / "tools" / "ffmpeg"
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    return shutil.which("ffmpeg")


def _font() -> str | None:
    for path in FONTS:
        if path.is_file():
            return str(path)
    return None


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace("'", r"\'").replace(":", r"\:")


def _wav_path(audio: str) -> Path | None:
    if not audio:
        return None
    name = Path(audio).name
    for candidate in (TTS_DIR / name, ROOT / audio, Path(audio)):
        if candidate.is_file():
            return candidate
    return None


def _wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 1
            return max(0.2, wf.getnframes() / float(rate))
    except Exception:
        return 1.5


def _wrap(text: str, width: int) -> list[str]:
    words = (text or "").replace("\n", " ").split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if len(trial) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
    if cur:
        lines.append(cur)
    return lines[:4] or [""]


def _run_ffmpeg(args: list[str], timeout: int = 180) -> None:
    bin_ = ffmpeg_bin()
    if not bin_:
        raise RuntimeError("ffmpeg missing")
    subprocess.run(
        [bin_, "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        capture_output=True,
        timeout=timeout,
    )


def _card_filter(speaker: str, line: str, topic: str) -> str:
    who = str(speaker or "reed").strip().lower() or "reed"
    font = _font()
    parts = [
        "drawbox=x=0:y=0:w=1280:h=96:color=0x162036:t=fill",
        "drawbox=x=0:y=552:w=1280:h=168:color=0x162036:t=fill",
    ]
    x = 40
    for key, name, color in CAST:
        fill = color if key == who else "0x323E54"
        parts.append(f"drawbox=x={x}:y=180:w=280:h=280:color={fill}:t=fill")
        x += 310
    if font:
        ff = f"fontfile={font}:"
        parts.append(f"drawtext={ff}text='THE SINGULARITY BLUES':fontcolor=white:fontsize=36:x=40:y=28")
        if topic:
            parts.append(f"drawtext={ff}text='{_esc(topic[:48])}':fontcolor=0xA0B0C6:fontsize=24:x=40:y=112")
        x = 40
        for key, name, _color in CAST:
            ink = "0x0C1220" if key == who else "0xB4BEC8"
            parts.append(f"drawtext={ff}text='{name.upper()}':fontcolor={ink}:fontsize=32:x={x + 24}:y=300")
            x += 310
        for i, wrapped in enumerate(_wrap(line, 52)):
            parts.append(
                f"drawtext={ff}text='{_esc(wrapped)}':fontcolor=white:fontsize=26:x=48:y={580 + i * 32}"
            )
    return ",".join(parts)


def encode_beat_ts(packet: dict[str, Any], index: int, dest: Path) -> float:
    beats = packet.get("beats") or []
    beat = beats[index]
    audio = _wav_path(str(beat.get("audio") or ""))
    if audio is None:
        raise FileNotFoundError(f"missing wav for beat {index}")
    duration = min(SEG_MAX, max(SEG_MIN, _wav_seconds(audio)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.ts")
    gop = max(30, int(round(duration * FPS)))
    vf = _card_filter(str(beat.get("speaker") or "reed"), str(beat.get("line") or ""), str(packet.get("topic") or ""))
    _run_ffmpeg(
        [
            "-f", "lavfi", "-t", f"{duration:.3f}", "-i", f"color=c=0x0C1220:s={WIDTH}x{HEIGHT}:r={FPS}",
            "-i", str(audio),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", "128k", "-ar", str(AAC_HZ), "-ac", "2",
            "-shortest", "-muxdelay", "0", "-muxpreload", "0",
            "-f", "mpegts", str(tmp),
        ]
    )
    tmp.replace(dest)
    return duration


def encode_hold_ts(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    gop = int(HOLD_SEC * FPS)
    vf = _card_filter("reed", "Stand by. The next scene is loading.", "The Singularity Blues")
    _run_ffmpeg(
        [
            "-f", "lavfi", "-t", f"{HOLD_SEC:.3f}", "-i", f"color=c=0x0C1220:s={WIDTH}x{HEIGHT}:r={FPS}",
            "-f", "lavfi", "-t", f"{HOLD_SEC:.3f}", "-i", f"anullsrc=r={AAC_HZ}:cl=stereo",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", "128k", "-ar", str(AAC_HZ), "-ac", "2",
            "-shortest", "-f", "mpegts", str(dest),
        ]
    )


def _episode_key(packet: dict[str, Any]) -> str:
    raw = packet.get("show_episode_id", packet.get("episode_id"))
    try:
        return f"ep{int(raw):04d}"
    except (TypeError, ValueError):
        return "ep0000"


def _seg_name(packet: dict[str, Any], index: int) -> str:
    return f"{_episode_key(packet)}_{index:02d}.ts"


def ensure_hold() -> Path:
    BROADCAST_DIR.mkdir(parents=True, exist_ok=True)
    path = BROADCAST_DIR / HOLD_NAME
    if path.is_file() and path.stat().st_size > 1000:
        return path
    encode_hold_ts(path)
    return path


def ensure_beat(packet: dict[str, Any], index: int) -> tuple[Path, float]:
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    dest = SEG_DIR / _seg_name(packet, index)
    meta = dest.with_suffix(".json")
    if dest.is_file() and dest.stat().st_size > 1000 and meta.is_file():
        try:
            return dest, float(json.loads(meta.read_text()).get("duration") or SEG_MIN)
        except Exception:
            pass
    with _encode_lock:
        if dest.is_file() and dest.stat().st_size > 1000 and meta.is_file():
            return dest, float(json.loads(meta.read_text()).get("duration") or SEG_MIN)
        duration = encode_beat_ts(packet, index, dest)
        meta.write_text(json.dumps({"duration": duration, "index": index}))
        return dest, duration


def _elapsed_in_current(packet: dict[str, Any], remaining: float) -> float:
    total = 0.0
    for beat in packet.get("beats") or []:
        path = _wav_path(str(beat.get("audio") or ""))
        total += min(SEG_MAX, max(SEG_MIN, _wav_seconds(path) if path else float(beat.get("duration_sec") or 1.5)))
    total = max(total, 8.0)
    return max(0.0, min(total, total - max(0.0, remaining)))


def _beat_index_at(packet: dict[str, Any], elapsed: float) -> int:
    t = 0.0
    beats = packet.get("beats") or []
    for i, beat in enumerate(beats):
        path = _wav_path(str(beat.get("audio") or ""))
        dur = min(SEG_MAX, max(SEG_MIN, _wav_seconds(path) if path else float(beat.get("duration_sec") or 1.5)))
        if elapsed < t + dur:
            return i
        t += dur
    return max(0, len(beats) - 1)


def upcoming_segments(limit_sec: float = LOOKAHEAD_SEC) -> list[dict[str, Any]]:
    from orchestrator.playlist import current as playlist_current, remaining_seconds

    packet = playlist_current() or {}
    beats = packet.get("beats") or []
    if not beats:
        return []
    remaining = remaining_seconds()
    elapsed = _elapsed_in_current(packet, remaining)
    start = _beat_index_at(packet, elapsed)
    out: list[dict[str, Any]] = []
    queued = 0.0
    for i in range(start, len(beats)):
        if queued >= limit_sec:
            break
        path, duration = ensure_beat(packet, i)
        out.append(
            {
                "file": path.name,
                "duration": duration,
                "episode": _episode_key(packet),
                "beat": i,
                "topic": packet.get("topic") or "",
            }
        )
        queued += duration
    return out


def write_live_playlist(segments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    BROADCAST_DIR.mkdir(parents=True, exist_ok=True)
    ensure_hold()
    segs = segments if segments is not None else upcoming_segments()
    if not segs:
        segs = [{"file": HOLD_NAME, "duration": HOLD_SEC, "episode": "hold", "beat": 0, "topic": ""}]
    target = int(max((s["duration"] for s in segs), default=HOLD_SEC)) + 1
    prev: dict[str, Any] = {}
    try:
        prev = json.loads((BROADCAST_DIR / WINDOW_NAME).read_text())
        seq = int(prev.get("media_sequence") or 0)
    except Exception:
        seq = 0
    first = segs[0]["file"]
    if first != prev.get("first_file"):
        seq += 1
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{target}",
        f"#EXT-X-MEDIA-SEQUENCE:{seq}",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    for item in segs:
        lines.append(f"#EXTINF:{float(item['duration']):.3f},")
        name = item["file"]
        href = f"/broadcast/{HOLD_NAME}" if name == HOLD_NAME else f"/broadcast/seg/{name}"
        lines.append(href)
    (BROADCAST_DIR / LIVE_NAME).write_text("\n".join(lines) + "\n")
    window = {
        "media_sequence": seq,
        "target_duration": target,
        "queue_seconds": sum(float(s["duration"]) for s in segs),
        "segments": segs,
        "hold": f"/broadcast/{HOLD_NAME}",
        "updated_at": time.time(),
        "first_file": first,
    }
    (BROADCAST_DIR / WINDOW_NAME).write_text(json.dumps(window, indent=2))
    return window


def status() -> dict[str, Any]:
    with _lock:
        window_path = BROADCAST_DIR / WINDOW_NAME
        try:
            data = json.loads(window_path.read_text()) if window_path.is_file() else {}
        except Exception:
            data = {}
        return {
            "ffmpeg": bool(ffmpeg_bin()),
            "hold": (BROADCAST_DIR / HOLD_NAME).is_file(),
            "live": (BROADCAST_DIR / LIVE_NAME).is_file(),
            "queue_seconds": float(data.get("queue_seconds") or 0),
            "segments": len(data.get("segments") or []),
        }


def _packager() -> None:
    while True:
        try:
            write_live_playlist()
        except Exception:
            try:
                ensure_hold()
                write_live_playlist([])
            except Exception:
                pass
        time.sleep(PACKAGER_SLEEP)


def start() -> None:
    if _started.is_set():
        return
    _started.set()
    BROADCAST_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_packager, daemon=True, name="tv-packager").start()
