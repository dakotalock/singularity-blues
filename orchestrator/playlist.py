"""Idle rerun playlist. Piper-voiced episodes loop; the writer only runs when prompted."""

from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, TTS_DIR
from orchestrator.tts import render, write_now_playing

PLAYLIST_PATH = DATA_DIR / "playlist.json"
GRACE_SEC = 1.75

_lock = threading.RLock()
_state: dict[str, Any] | None = None


def _packet_wav_ok(packet: dict[str, Any]) -> bool:
    beats = packet.get("beats") or []
    if len(beats) < 4:
        return False
    for beat in beats:
        audio = str(beat.get("audio") or "")
        if not audio:
            return False
        name = Path(audio).name
        if (TTS_DIR / name).is_file():
            continue
        candidate = ROOT / audio
        if candidate.is_file():
            continue
        return False
    return True


def _duration(packet: dict[str, Any]) -> float:
    total = 0.0
    for beat in packet.get("beats") or []:
        total += float(beat.get("duration_sec") or 1.5)
    return max(8.0, total)


def _empty_state() -> dict[str, Any]:
    return {"packets": [], "index": 0, "airing": 0, "started_at": 0.0}


def _load() -> dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    if PLAYLIST_PATH.is_file():
        try:
            raw = json.loads(PLAYLIST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        packets = [p for p in (raw.get("packets") or []) if isinstance(p, dict) and _packet_wav_ok(p)]
        _state = {
            "packets": packets,
            "index": int(raw.get("index") or 0),
            "airing": int(raw.get("airing") or 0),
            "started_at": float(raw.get("started_at") or 0.0),
        }
        if _state["packets"]:
            _state["index"] %= len(_state["packets"])
        else:
            _state["index"] = 0
    else:
        _state = _empty_state()
    return _state


def _save(state: dict[str, Any]) -> None:
    PLAYLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PLAYLIST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(PLAYLIST_PATH)


def _serve_packet(state: dict[str, Any]) -> dict[str, Any]:
    packets = state["packets"]
    if not packets:
        return {"episode_id": None, "scene": None, "topic": None, "beats": []}
    src = packets[state["index"] % len(packets)]
    out = deepcopy(src)
    real_id = src.get("episode_id")
    airing = int(state["airing"] or 1)
    # Godot treats episode_id changes as "play this now". Airing bumps make reruns restart.
    out["show_episode_id"] = real_id
    out["episode_id"] = airing
    out["rerun"] = bool(src.get("source") == "seed") or airing != real_id
    return out


def _publish(state: dict[str, Any]) -> dict[str, Any]:
    packet = _serve_packet(state)
    if packet.get("beats"):
        write_now_playing(packet, NOW_PLAYING_PATH)
    return packet


def _advance_if_due(state: dict[str, Any], now: float) -> None:
    packets = state["packets"]
    if not packets:
        return
    idx = state["index"] % len(packets)
    started = float(state["started_at"] or 0.0)
    if started <= 0:
        state["started_at"] = now
        state["index"] = idx
        return
    limit = _duration(packets[idx]) + GRACE_SEC
    if now - started < limit:
        return
    state["index"] = (idx + 1) % len(packets)
    state["airing"] = int(state["airing"] or 0) + 1
    state["started_at"] = now
    _save(state)
    _publish(state)


def current() -> dict[str, Any]:
    with _lock:
        state = _load()
        _advance_if_due(state, time.time())
        return _serve_packet(state)


def pin(packet: dict[str, Any]) -> dict[str, Any]:
    """Make this voiced episode now-playing and append it to the rerun rotation."""
    if not packet or not packet.get("beats"):
        return current()
    with _lock:
        state = _load()
        stored = deepcopy(packet)
        stored["show_episode_id"] = stored.get("episode_id")
        packets = state["packets"]
        real_id = stored.get("episode_id")
        replaced = False
        if real_id is not None:
            for i, existing in enumerate(packets):
                if existing.get("episode_id") == real_id:
                    packets[i] = stored
                    state["index"] = i
                    replaced = True
                    break
        if not replaced:
            packets.append(stored)
            state["index"] = len(packets) - 1
        state["airing"] = int(state["airing"] or 0) + 1
        state["started_at"] = time.time()
        _save(state)
        return _publish(state)


def ensure_voiced_boot(mem) -> dict[str, Any]:
    """If the playlist is empty, Piper (or tone) the seed scene. No writer call."""
    from copy import deepcopy as dc

    from orchestrator.gemini import TOASTER_APPLICATION_SCENE

    with _lock:
        state = _load()
        if state["packets"]:
            if not state.get("started_at"):
                state["started_at"] = time.time()
                if not state.get("airing"):
                    state["airing"] = 1
                _save(state)
            return _publish(state)

    scene = dc(TOASTER_APPLICATION_SCENE)
    scene["source"] = "seed"
    episode_id = mem.insert_episode(scene.get("topic") or "seed", "seed", scene)
    packet = render(scene, episode_id)
    packet["source"] = "seed"
    return pin(packet)


def snapshot() -> dict[str, Any]:
    with _lock:
        state = _load()
        return {
            "count": len(state["packets"]),
            "index": state["index"],
            "airing": state["airing"],
            "topics": [p.get("topic") for p in state["packets"]],
        }
