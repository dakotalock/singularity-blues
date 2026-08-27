"""Render each beat to wav: Piper voices if present, else pitch-shift, else ffmpeg/python tones."""

from __future__ import annotations

import hashlib
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
MIN_WAV_SEC = 0.2


def _duration_estimate(line: str) -> float:
    words = max(1, len((line or "").split()))
    return max(0.7, min(8.0, 0.32 * words + 0.35))


def _piper_timeout_sec(text: str) -> int:
    """Long timestamp lines need more than 60s; scale with word count."""
    words = max(1, len((text or "").split()))
    return int(max(60, min(180, 40 + words * 2)))


def _wav_name(episode_id: int, index: int, speaker: str, line: str) -> str:
    speaker = str(speaker or "reed").strip().lower() or "reed"
    digest = hashlib.sha256(f"{speaker}\n{line}".encode("utf-8")).hexdigest()[:8]
    return f"ep{int(episode_id):04d}_{int(index):02d}_{speaker}_{digest}.wav"


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate() or SAMPLE_RATE
        return max(MIN_WAV_SEC, wf.getnframes() / float(rate))


def _usable_wav(path: Path) -> bool:
    """True only for PCM s16 wavs with real audio. Rejects headers, float, and stubs."""
    if not path.is_file():
        return False
    try:
        with wave.open(str(path), "rb") as wf:
            nframes = wf.getnframes()
            if nframes <= 0 or wf.getsampwidth() != 2:
                return False
            rate = wf.getframerate() or SAMPLE_RATE
            return (nframes / float(rate)) >= MIN_WAV_SEC
    except (wave.Error, EOFError, OSError, struct.error):
        return False


def _normalize_wav(path: Path) -> bool:
    """Rewrite as PCM s16le 22050 Hz mono so Godot WavLoader (no IEEE float) can play it."""
    if not path.is_file():
        return False
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return _usable_wav(path)
    tmp = path.with_name(path.name + ".norm.wav")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(path),
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        if tmp.is_file() and tmp.stat().st_size > 44:
            tmp.replace(path)
            return _usable_wav(path)
    except (subprocess.SubprocessError, OSError):
        pass
    _safe_unlink(tmp)
    return _usable_wav(path)


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
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-af",
        "volume=0.18,afade=t=in:st=0:d=0.04,afade=t=out:st={:.3f}:d=0.08".format(max(0.05, duration - 0.08)),
        str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=20)
        return _usable_wav(path)
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
