"""Render each beat to wav: Piper voices if present, else pitch-shift, else ffmpeg/python tones."""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

from orchestrator import NOW_PLAYING_PATH, PIPER_BIN, ROOT, TTS_DIR, VOICES_DIR

VOICE_FILES = {
    "reed": "en_US-ryan-medium.onnx",      # low, tired dad
    "maris": "en_US-amy-medium.onnx",      # even, precise
    "jinx": "en_GB-alba-medium.onnx",      # bright, other accent
    "quill": "en_US-lessac-medium.onnx",   # earnest, different male
}

# Last-resort sine frequencies (Hz) if Piper models are missing.
TONE_HZ = {"reed": 180, "maris": 260, "jinx": 420, "quill": 330}
PITCH_SHIFT = {"reed": 0.86, "maris": 1.04, "jinx": 1.18, "quill": 1.10}
SAMPLE_RATE = 22050


def _duration_estimate(line: str) -> float:
    words = max(1, len((line or "").split()))
    return max(0.7, min(8.0, 0.32 * words + 0.35))


def wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate() or SAMPLE_RATE
        return max(0.2, wf.getnframes() / float(rate))


def _write_tone_wav(path: Path, duration: float, hz: float) -> None:
    n = int(SAMPLE_RATE * duration)
    amp = 8000
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for i in range(n):
            t = i / SAMPLE_RATE
            # Soft envelope so it isn't a click; slight AM so it feels spoken-ish.
            env = min(1.0, i / (0.02 * SAMPLE_RATE), (n - i) / (0.04 * SAMPLE_RATE))
            env = max(0.0, min(1.0, env))
            sample = env * amp * math.sin(2 * math.pi * hz * t) * (0.7 + 0.3 * math.sin(2 * math.pi * 3 * t))
            frames += struct.pack("<h", int(max(-32767, min(32767, sample))))
        wf.writeframes(frames)


def _ffmpeg_tone(path: Path, duration: float, hz: float) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={hz}:sample_rate={SAMPLE_RATE}:duration={duration:.3f}",
        "-af",
        "volume=0.18,afade=t=in:st=0:d=0.04,afade=t=out:st={:.3f}:d=0.08".format(max(0.05, duration - 0.08)),
        str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=20)
        return path.is_file() and path.stat().st_size > 44
    except (subprocess.SubprocessError, OSError):
        return False


def _available_models() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for speaker, filename in VOICE_FILES.items():
        candidate = VOICES_DIR / filename
        if candidate.is_file():
            found[speaker] = candidate
    if found:
        return found
    # Any onnx in voices dir.
    if VOICES_DIR.is_dir():
        onnxs = sorted(VOICES_DIR.glob("*.onnx"))
        if onnxs:
            speakers = list(VOICE_FILES)
            for i, speaker in enumerate(speakers):
                found[speaker] = onnxs[i % len(onnxs)]
    return found


def piper_available() -> bool:
    return PIPER_BIN.is_file() and os.access(PIPER_BIN, os.X_OK)


def _run_piper(text: str, model: Path, out: Path) -> bool:
    env = os.environ.copy()
    libdir = str(PIPER_BIN.parent)
    env["LD_LIBRARY_PATH"] = libdir + ((":" + env["LD_LIBRARY_PATH"]) if env.get("LD_LIBRARY_PATH") else "")
    try:
        proc = subprocess.run(
            [str(PIPER_BIN), "--model", str(model), "--output_file", str(out)],
            input=(text.strip() + "\n").encode("utf-8"),
            capture_output=True,
            timeout=60,
            env=env,
            cwd=str(PIPER_BIN.parent),
        )
        return proc.returncode == 0 and out.is_file() and out.stat().st_size > 44
    except (subprocess.SubprocessError, OSError):
        return False


def _pitch_shift(src: Path, dest: Path, factor: float) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or abs(factor - 1.0) < 0.02:
        if src != dest:
            shutil.copyfile(src, dest)
        return dest.is_file()
    rate = int(SAMPLE_RATE * factor)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-af",
        f"asetrate={rate},aresample={SAMPLE_RATE},atempo={1/factor:.4f}",
        str(dest),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=20)
        return dest.is_file()
    except (subprocess.SubprocessError, OSError):
        shutil.copyfile(src, dest)
        return dest.is_file()


def _render_line(speaker: str, line: str, dest: Path, models: dict[str, Path]) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = _duration_estimate(line)
    if piper_available() and models:
        model = models.get(speaker) or next(iter(models.values()))
        if _run_piper(line, model, dest):
            # If we reused a single model, pitch-shift into character.
            unique_models = {p.resolve() for p in models.values()}
            if len(unique_models) == 1:
                shifted = dest.with_suffix(".shift.wav")
                factor = PITCH_SHIFT.get(speaker, 1.0)
                if _pitch_shift(dest, shifted, factor):
                    shifted.replace(dest)
            return wav_duration_sec(dest)
    hz = TONE_HZ.get(speaker, 300)
    if _ffmpeg_tone(dest, duration, hz):
        return wav_duration_sec(dest)
    _write_tone_wav(dest, duration, hz)
    return wav_duration_sec(dest)


def render(scene: dict[str, Any], episode_id: int, out_dir: Path | None = None) -> dict[str, Any]:
    """Write per-beat wavs and return a Godot now_playing packet (also written to disk)."""
    tts_dir = Path(out_dir) if out_dir else TTS_DIR
    tts_dir.mkdir(parents=True, exist_ok=True)
    models = _available_models()
    beats_out: list[dict[str, Any]] = []
    for i, beat in enumerate(scene.get("beats") or []):
        speaker = beat.get("speaker") or "reed"
        line = beat.get("line") or "..."
        filename = f"ep{int(episode_id):04d}_{i:02d}_{speaker}.wav"
        dest = tts_dir / filename
        duration = _render_line(speaker, line, dest, models)
        rel = dest.relative_to(ROOT).as_posix()
        beats_out.append(
            {
                "speaker": speaker,
                "line": line,
                "emotion": beat.get("emotion") or "calm",
                "animation": beat.get("animation") or "talking",
                "target": beat.get("target"),
                "camera": beat.get("camera") or "auto",
                "audio": rel,
                "duration_sec": round(float(duration), 3),
            }
        )
    packet = {
        "episode_id": int(episode_id),
        "scene": scene.get("scene") or "living_room",
        "topic": scene.get("topic") or "",
        "beats": beats_out,
    }
    return packet


def write_now_playing(packet: dict[str, Any], path: Path | None = None) -> Path:
    target = Path(path) if path else NOW_PLAYING_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    import json

    tmp.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target
