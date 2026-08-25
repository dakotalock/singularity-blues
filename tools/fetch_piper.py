#!/usr/bin/env python3
"""Download Piper linux x86_64 + the four sitcom voices if missing.

Used on Render at build. Models stay out of git (too large). Never prints URLs
with credentials; these are public Hugging Face / GitHub release files.
"""
from __future__ import annotations

import os
import stat
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER_DIR = ROOT / "tools" / "piper"
VOICES_DIR = ROOT / "tts" / "voices"
PIPER_TGZ_URL = (
    "https://github.com/rhasspy/piper/releases/download/"
    "2023.11.14-2/piper_linux_x86_64.tar.gz"
)
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOICES = {
    "en_US-ryan-medium.onnx": f"{HF}/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
    "en_US-ryan-medium.onnx.json": f"{HF}/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json",
    "en_US-amy-medium.onnx": f"{HF}/en/en_US/amy/medium/en_US-amy-medium.onnx",
    "en_US-amy-medium.onnx.json": f"{HF}/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
    "en_GB-alba-medium.onnx": f"{HF}/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
    "en_GB-alba-medium.onnx.json": f"{HF}/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json",
    "en_US-lessac-medium.onnx": f"{HF}/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en_US-lessac-medium.onnx.json": f"{HF}/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print("fetch", dest.name)
    req = urllib.request.Request(url, headers={"User-Agent": "singularity-blues-build"})
    with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def _ensure_piper() -> None:
    binary = PIPER_DIR / "piper"
    if binary.is_file() and os.access(binary, os.X_OK):
        print("piper binary present")
        return
    tgz = ROOT / "tools" / "piper_linux_x86_64.tar.gz"
    _download(PIPER_TGZ_URL, tgz)
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz, "r:gz") as tf:
        tf.extractall(ROOT / "tools")
    if binary.is_file():
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    try:
        tgz.unlink()
    except OSError:
        pass
    print("piper extracted", binary, "ok" if binary.is_file() else "MISSING")


def _ensure_voices() -> None:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in VOICES.items():
        dest = VOICES_DIR / name
        if dest.is_file() and dest.stat().st_size > 100:
            print("voice present", name)
            continue
        _download(url, dest)
        print("voice wrote", name, dest.stat().st_size)


def main() -> None:
    _ensure_piper()
    _ensure_voices()
    binary = PIPER_DIR / "piper"
    onnxs = list(VOICES_DIR.glob("*.onnx"))
    print("piper_ok", binary.is_file(), "voices", len(onnxs))


if __name__ == "__main__":
    main()
