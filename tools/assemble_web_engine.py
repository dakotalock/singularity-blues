#!/usr/bin/env python3
"""Rebuild web/stage engine files from committed text parts."""
from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "web" / "stage"
PARTS = ROOT / "tools" / "web-engine-parts"


def main() -> None:
    STAGE.mkdir(parents=True, exist_ok=True)
    pck_b64 = PARTS / "index.pck.b64"
    pck_dest = STAGE / "index.pck"
    if pck_b64.is_file() and (not pck_dest.is_file() or pck_dest.stat().st_size < 1000):
        pck_dest.write_bytes(base64.b64decode(pck_b64.read_text().encode("ascii")))
        print("wrote", pck_dest, pck_dest.stat().st_size)

    dest = STAGE / "index.wasm"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print("index.wasm already present", dest.stat().st_size)
        return
    chunks = sorted(PARTS.glob("part-*.b64"))
    if not chunks:
        print("no web-engine-parts; skip wasm")
        return
    raw = b"".join(base64.b64decode(p.read_text().encode("ascii")) for p in chunks)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        wasm = zf.read("godot.wasm")
    dest.write_bytes(wasm)
    print("wrote", dest, dest.stat().st_size)


if __name__ == "__main__":
    main()
