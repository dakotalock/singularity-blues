"""Idle rerun playlist. Piper-voiced episodes loop; the writer only runs when prompted."""

from __future__ import annotations

import json
import random
import threading
import time
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, TTS_DIR
from orchestrator.tts import render, write_now_playing

PLAYLIST_PATH = DATA_DIR / "playlist.json"
GRACE_SEC = 12.0
HOLD_SEC = 0.65
ENTER_WALK_SEC = 2.8
LEAVE_SEC = 1.65
LAST_BEAT_PAD = 1.0
DURATION_MULT = 1.08

_lock = threading.RLock()
_state: dict[str, Any] | None = None
_rng = random.Random()


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


def _wav_seconds(path: Path | str) -> float | None:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


def _beat_audio_path(audio: str) -> Path | None:
    if not audio:
        return None
    name = Path(audio).name
    for candidate in (TTS_DIR / name, ROOT / audio):
        if candidate.is_file():
            return candidate
    return None


def _duration(packet: dict[str, Any]) -> float:
    # Over-estimate vs Godot: holds, reaction shots, last-beat camera, walking.
    # A few seconds of idle is better than cutting the episode short.
    speech = 0.0
    motion = 0.0
    beats = packet.get("beats") or []
    for beat in beats:
        audio = str(beat.get("audio") or "")
        wav_len = None
        path = _beat_audio_path(audio)
        if path is not None:
            wav_len = _wav_seconds(path)
        if wav_len is not None:
            speech += wav_len
        else:
            speech += float(beat.get("duration_sec") or 1.5)
        speech += HOLD_SEC
        anim = str(beat.get("animation") or "").lower()
        if anim in ("enter", "walking"):
            motion += ENTER_WALK_SEC
        elif anim == "leave":
            motion += LEAVE_SEC
    total = speech * DURATION_MULT + motion
    if beats:
        total += LAST_BEAT_PAD
    return max(8.0, total)


def _random_index(packets: list[dict[str, Any]], avoid: int | None = None) -> int:
    """Random rerun. Prefer real episodes over the seed when both exist."""
    n = len(packets)
    if n <= 0:
        return 0
    if n == 1:
        return 0
    preferred = [i for i, pkt in enumerate(packets) if pkt.get("source") != "seed"]
    pool = preferred or list(range(n))
    if avoid is not None and len(pool) > 1:
        narrowed = [i for i in pool if i != avoid]
        if narrowed:
            pool = narrowed
    return _rng.choice(pool)


def _empty_state() -> dict[str, Any]:
    return {"packets": [], "index": 0, "airing": 0, "started_at": 0.0, "queued": None}


def _parse_queued(raw: Any) -> int | None:
    if raw is None or raw is False:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


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
            "queued": _parse_queued(raw.get("queued")),
        }
        if _state["packets"]:
            _state["index"] %= len(_state["packets"])
        else:
            _state["index"] = 0
    else:
        _state = _empty_state()
    if "queued" not in _state:
        _state["queued"] = None
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


def _playing(state: dict[str, Any], now: float) -> bool:
    packets = state["packets"]
    if not packets:
        return False
    started = float(state.get("started_at") or 0.0)
    if started <= 0:
        return False
    idx = int(state.get("index") or 0) % len(packets)
    return now - started < _duration(packets[idx]) + GRACE_SEC


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
    queued = state.get("queued")
    n = len(packets)
    if isinstance(queued, int) and 0 <= queued < n:
        state["index"] = queued
        state["queued"] = None
    else:
        state["index"] = _random_index(packets, avoid=idx)
        state["queued"] = None
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
        new_idx: int | None = None
        if real_id is not None:
            for i, existing in enumerate(packets):
                if existing.get("episode_id") == real_id:
                    packets[i] = stored
                    new_idx = i
                    break
        if new_idx is None:
            packets.append(stored)
            new_idx = len(packets) - 1
        now = time.time()
        if _playing(state, now):
            state["queued"] = new_idx
            _save(state)
            try:
                from orchestrator import archive
                archive.upsert_episode(stored)
            except Exception:
                pass
            return _serve_packet(state)
        state["index"] = new_idx
        state["airing"] = int(state["airing"] or 0) + 1
        state["started_at"] = now
        state["queued"] = None
        _save(state)
        try:
            from orchestrator import archive
            archive.upsert_episode(stored)
        except Exception:
            pass
        return _publish(state)


def _ingest_archived(items: list[dict[str, Any]]) -> None:
    """Re-voice stored scripts into the local playlist. No writer."""
    if not items:
        return
    from orchestrator.tts import render as render_scene

    with _lock:
        state = _load()
        have = {p.get("episode_id") for p in state["packets"]}
    fresh: list[dict[str, Any]] = []
    for item in items:
        eid = item.get("id")
        scene = item.get("scene") or {}
        if eid in have or not scene.get("beats"):
            continue
        packet = render_scene(scene, int(eid))
        packet["source"] = scene.get("source") or "viewer"
        fresh.append(packet)
    if not fresh:
        return
    with _lock:
        state = _load()
        have = {p.get("episode_id") for p in state["packets"]}
        for packet in fresh:
            if packet.get("episode_id") not in have:
                state["packets"].append(packet)
        _save(state)


def ensure_voiced_boot(mem) -> dict[str, Any]:
    """Start on a random rerun. Seed is last resort when the pool is empty. No writer call."""
    from copy import deepcopy as dc

    from orchestrator import archive
    from orchestrator.gemini import TOASTER_APPLICATION_SCENE

    try:
        archive.init()
        try:
            mem.restore_from_archive()
        except Exception:
            pass
        _ingest_archived(archive.list_scenes())
    except Exception:
        pass

    with _lock:
        state = _load()
        if state["packets"]:
            state["index"] = _random_index(state["packets"])
            state["airing"] = max(1, int(state["airing"] or 0) + 1)
            state["started_at"] = time.time()
            _save(state)
            return _publish(state)

    recovered = _recover_random_from_db(mem)
    if recovered is not None:
        return pin(recovered)

    scene = dc(TOASTER_APPLICATION_SCENE)
    scene["source"] = "seed"
    episode_id = mem.insert_episode(scene.get("topic") or "seed", "seed", scene)
    packet = render(scene, episode_id)
    packet["source"] = "seed"
    return pin(packet)


def _recover_random_from_db(mem) -> dict[str, Any] | None:
    """Rebuild one random past episode from sqlite if wavs/playlist were empty."""
    try:
        rows = mem.conn.execute(
            "SELECT id, topic, source, scene_json FROM episodes "
            "WHERE scene_json IS NOT NULL ORDER BY id DESC LIMIT 50"
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    mapped = []
    for row in rows:
        try:
            scene = json.loads(row["scene_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not scene:
            continue
        mapped.append((int(row["id"]), str(row["source"] or ""), scene))
    if not mapped:
        return None
    preferred = [m for m in mapped if m[1] != "seed"]
    pool = preferred or mapped
    episode_id, source, scene = _rng.choice(pool)
    packet = render(scene, episode_id)
    packet["source"] = source or "viewer"
    return packet


def snapshot() -> dict[str, Any]:
    with _lock:
        state = _load()
        return {
            "count": len(state["packets"]),
            "index": state["index"],
            "airing": state["airing"],
            "topics": [p.get("topic") for p in state["packets"]],
        }
