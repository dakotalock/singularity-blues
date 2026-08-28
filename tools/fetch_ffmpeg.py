#!/usr/bin/env python3
"""Download a static linux amd64 ffmpeg into tools/ffmpeg if missing.

Used on Render at build so the TV packager can emit H.264/AAC segments.
"""
from __future__ import annotations

import os
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tools" / "ffmpeg"
FONT = ROOT / "tools" / "DejaVuSans.ttf"
URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
FONT_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf"


def _download(url: str, dest: Path, timeout: int = 180) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "singularity-blues-build"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def _ensure_ffmpeg() -> None:
    if DEST.is_file() and os.access(DEST, os.X_OK) and DEST.stat().st_size > 1000:
        print("ffmpeg present")
        return
    print("fetch ffmpeg static")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tarball = Path(tmp) / "ffmpeg.tar.xz"
            _download(URL, tarball, timeout=180)
            with tarfile.open(tarball, "r:xz") as tf:
                for member in tf.getmembers():
                    name = Path(member.name).name
                    if name == "ffmpeg" and member.isfile():
                        tf.extract(member, path=tmp)
                        src = Path(tmp) / member.name
                        src.replace(DEST)
                        break
    except Exception as exc:
        # requirements.txt includes imageio-ffmpeg, so a transient mirror
        # failure cannot break the entire public-site deployment.
        print("static ffmpeg fetch failed; use wheel fallback:", type(exc).__name__)
        try:
            import imageio_ffmpeg  # type: ignore

            shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), DEST)
        except Exception as fallback_exc:
            raise SystemExit("ffmpeg fetch and wheel fallback both failed") from fallback_exc
    if DEST.is_file():
        DEST.chmod(DEST.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print("ffmpeg extracted", DEST.stat().st_size)
    else:
        raise SystemExit("ffmpeg extract failed")


def _ensure_font() -> None:
    if FONT.is_file() and FONT.stat().st_size > 1000:
        print("font present")
        return
    print("fetch DejaVuSans")
    _download(FONT_URL, FONT, timeout=120)
    print("font wrote", FONT.stat().st_size)


def main() -> None:
    _ensure_ffmpeg()
    try:
        _ensure_font()
    except Exception as exc:
        # Pillow can still use a system or built-in font; missing title-card
        # typography must not take the interactive show offline.
        print("font fetch skipped:", type(exc).__name__)


if __name__ == "__main__":
    main()
