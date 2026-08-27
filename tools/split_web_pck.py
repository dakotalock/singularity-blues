#!/usr/bin/env python3
"""Encode the current Godot Web PCK into Git-friendly committed text chunks."""

from __future__ import annotations

import base64
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PCK = ROOT / "web" / "stage" / "index.pck"
PARTS = ROOT / "tools" / "web-engine-parts"
CHUNK_CHARS = 15_000


def main() -> None:
    if not PCK.is_file():
        raise SystemExit(f"missing {PCK}")
    PARTS.mkdir(parents=True, exist_ok=True)
    encoded = base64.b64encode(PCK.read_bytes()).decode("ascii")
    for old in PARTS.glob("index.pck.part-*.b64"):
        old.unlink()
    chunks = [encoded[i : i + CHUNK_CHARS] for i in range(0, len(encoded), CHUNK_CHARS)]
    for number, chunk in enumerate(chunks, start=1):
        path = PARTS / f"index.pck.part-{number:02d}.b64"
        path.write_text(chunk, encoding="ascii")
    reconstructed = b"".join(
        base64.b64decode(path.read_text(encoding="ascii"))
        for path in sorted(PARTS.glob("index.pck.part-*.b64"))
    )
    if reconstructed != PCK.read_bytes():
        raise SystemExit("chunk verification failed")
    print(f"wrote {len(chunks)} verified chunks for {PCK.stat().st_size} bytes")


if __name__ == "__main__":
    main()
