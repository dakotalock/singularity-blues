#!/usr/bin/env python3
"""Rebuild web/stage engine files from committed text parts or Godot templates."""
from __future__ import annotations

import base64
import io
import re
import struct
import urllib.request
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "web" / "stage"
PARTS = ROOT / "tools" / "web-engine-parts"
TEMPLATES_TPZ = (
    "https://github.com/godotengine/godot-builds/releases/download/"
    "4.4.1-stable/Godot_v4.4.1-stable_export_templates.tpz"
)
UA = {"User-Agent": "singularity-blues-build"}


def _decode_joined(paths: list[Path]) -> bytes:
    return b"".join(base64.b64decode(p.read_text().encode("ascii")) for p in paths)


def _patch_stage_index(html: bytes, *, pck_size: int | None = None) -> bytes:
    """Put Private Showing in the real POST body without wrapping fetch()."""
    private_field = (
        b"private_showing: !!(document.getElementById('sitcom-private') "
        b"&& document.getElementById('sitcom-private').checked)"
    )
    if private_field not in html:
        needle = b"ltm_pin: !!(pinEl && pinEl.checked)"
        if needle not in html:
            raise RuntimeError("stage-index prompt body hook not found")
        html = html.replace(needle, needle + b",\n\t\t\t\t\t" + private_field, 1)
    if pck_size is not None:
        html, count = re.subn(rb'"index\.pck":\d+', f'"index.pck":{int(pck_size)}'.encode(), html, count=1)
        if count != 1:
            raise RuntimeError("stage-index pck size hook not found")
    return html


def _built_pck_size() -> int | None:
    pck = STAGE / "index.pck"
    if pck.is_file():
        return pck.stat().st_size
    chunks = sorted(PARTS.glob("index.pck.part-*.b64"))
    if chunks:
        return len(_decode_joined(chunks))
    whole = PARTS / "index.pck.b64"
    if whole.is_file():
        return len(base64.b64decode(whole.read_text().encode("ascii")))
    return None


def _write_stage_index() -> None:
    dest = STAGE / "index.html"
    chunks = sorted(PARTS.glob("stage-index.part-*.b64"))
    if not chunks:
        print("no stage-index parts; skip")
        return
    html = _decode_joined(chunks)
    if len(html) < 30000 or not re.search(rb'"index\.pck":\d+', html):
        raise RuntimeError(f"stage-index assemble too small or missing pck: {len(html)}")
    html = _patch_stage_index(html, pck_size=_built_pck_size())
    dest.write_bytes(html)
    print("wrote", dest, dest.stat().st_size)


def _write_pck() -> None:
    dest = STAGE / "index.pck"
    if dest.is_file() and dest.stat().st_size > 1000:
        print("index.pck already present", dest.stat().st_size)
        return
    whole = PARTS / "index.pck.b64"
    chunks = sorted(PARTS.glob("index.pck.part-*.b64"))
    if whole.is_file():
        dest.write_bytes(base64.b64decode(whole.read_text().encode("ascii")))
    elif chunks:
        dest.write_bytes(_decode_joined(chunks))
    else:
        print("no pck parts; skip")
        return
    print("wrote", dest, dest.stat().st_size)


def _extract_engine(zbytes: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
        mapping = {
            "godot.wasm": STAGE / "index.wasm",
            "godot.js": STAGE / "index.js",
            "godot.audio.worklet.js": STAGE / "index.audio.worklet.js",
            "godot.audio.position.worklet.js": STAGE / "index.audio.position.worklet.js",
        }
        for inner, dest in mapping.items():
            if inner not in zf.namelist():
                continue
            if dest.is_file() and dest.stat().st_size > 100:
                print(dest.name, "already present", dest.stat().st_size)
                continue
            dest.write_bytes(zf.read(inner))
            print("wrote", dest, dest.stat().st_size)


def _engine_from_parts() -> bool:
    chunks = sorted(p for p in PARTS.glob("part-*.b64") if "pck" not in p.name)
    if not chunks:
        return False
    print("assembling wasm from", len(chunks), "parts")
    _extract_engine(_decode_joined(chunks))
    return True


def _http_range(url: str, start: int, end: int) -> bytes:
    req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def _engine_from_official_templates() -> None:
    print("fetching Godot 4.4.1 web_nothreads_release via range requests")
    head = urllib.request.Request(TEMPLATES_TPZ, method="HEAD", headers=UA)
    with urllib.request.urlopen(head, timeout=60) as resp:
        final = resp.geturl()
        size = int(resp.headers["Content-Length"])
    tail_n = 64 * 1024
    tail = _http_range(final, size - tail_n, size - 1)
    idx = tail.rfind(b"PK\x05\x06")
    if idx < 0:
        raise RuntimeError("tpz EOCD not found")
    _disk, _cd_disk, _nthis, _ntotal, cd_size, cd_off, _comm = struct.unpack_from(
        "<HHHHIIH", tail, idx + 4
    )
    cd = _http_range(final, cd_off, cd_off + cd_size - 1)
    pos = 0
    wanted = None
    while pos + 46 <= len(cd):
        if cd[pos : pos + 4] != b"PK\x01\x02":
            break
        (
            _ver_made,
            _ver_need,
            _flag,
            _method,
            _time,
            _date,
            _crc,
            csz,
            _usz,
            nlen,
            elen,
            clen,
            _disk_s,
            _iattr,
            _eattr,
            loff,
        ) = struct.unpack_from("<HHHHHHIIIHHHHHII", cd, pos + 4)
        name = cd[pos + 46 : pos + 46 + nlen].decode("utf-8", "replace")
        if name.endswith("templates/web_nothreads_release.zip") or name == "templates/web_nothreads_release.zip":
            wanted = (loff, csz)
        pos += 46 + nlen + elen + clen
    if wanted is None:
        raise RuntimeError("web_nothreads_release.zip not in tpz")
    loff, csz = wanted
    lh = _http_range(final, loff, loff + 29)
    lnlen, lelen = struct.unpack_from("<HH", lh, 26)
    method = struct.unpack_from("<H", lh, 8)[0]
    data_start = loff + 30 + lnlen + lelen
    payload = _http_range(final, data_start, data_start + csz - 1)
    print("downloaded compressed template", len(payload), "method", method)
    if method == 0:
        zbytes = payload
    elif method == 8:
        zbytes = zlib.decompress(payload, -15)
    else:
        raise RuntimeError(f"unsupported zip method {method}")
    _extract_engine(zbytes)



def _expose_audio() -> None:
    js = STAGE / "index.js"
    if not js.is_file():
        return
    text = js.read_text(encoding="utf-8", errors="replace")
    needle = "GodotAudio.ctx=ctx;"
    if "window.GodotAudio=GodotAudio" in text:
        print("GodotAudio already exposed")
        return
    if needle not in text:
        print("GodotAudio.ctx=ctx not found")
        return
    js.write_text(text.replace(needle, "GodotAudio.ctx=ctx;window.GodotAudio=GodotAudio;", 1), encoding="utf-8")
    print("exposed window.GodotAudio")


def main() -> None:
    STAGE.mkdir(parents=True, exist_ok=True)
    PARTS.mkdir(parents=True, exist_ok=True)
    _write_stage_index()
    _write_pck()
    dest = STAGE / "index.wasm"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print("index.wasm already present", dest.stat().st_size)
        js = STAGE / "index.js"
        if not js.is_file() or js.stat().st_size < 1000:
            if not _engine_from_parts():
                _engine_from_official_templates()
        _expose_audio()
        return
    if not _engine_from_parts():
        _engine_from_official_templates()
    _expose_audio()


if __name__ == "__main__":
    main()
