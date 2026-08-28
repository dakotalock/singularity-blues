#!/usr/bin/env python3
"""Download a static linux amd64 ffmpeg into tools/ffmpeg if missing.

Used on Render at build so the TV packager can emit H.264/AAC segments.
"""
from __future__ import annotations

import os
import stat
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tools" / "ffmpeg"
# Public static build (GPL). ~40-80MB.
URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"


def main() -> None:
    if DEST.is_file() and os.access(DEST, os.X_OK) and DEST.stat().st_size > 1000:
        print("ffmpeg present")
        return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print("fetch ffmpeg static")
    req = urllib.request.Request(URL, headers={"User-Agent": "singularity-blues-build"})
    with tempfile.TemporaryDirectory() as tmp:
        tarball = Path(tmp) / "ffmpeg.tar.xz"
        with urllib.request.urlopen(req, timeout=180) as resp, tarball.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
        with tarfile.open(tarball, "r:xz") as tf:
            for member in tf.getmembers():
                name = Path(member.name).name
                if name == "ffmpeg" and member.isfile():
                    tf.extract(member, path=tmp)
                    src = Path(tmp) / member.name
                    src.replace(DEST)
                    break
    if DEST.is_file():
        DEST.chmod(DEST.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print("ffmpeg extracted", DEST.stat().st_size)
    else:
        raise SystemExit("ffmpeg extract failed")


if __name__ == "__main__":
    main()
