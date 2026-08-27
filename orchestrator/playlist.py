"""Idle rerun playlist. Piper-voiced episodes loop; the writer only runs when prompted."""

from __future__ import annotations

import json
import math
import random
import re
import threading
import time
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any

from orchestrator import DATA_DIR, NOW_PLAYING_PATH, ROOT, TTS_DIR
from orchestrator.tts import write_now_playing

PLAYLIST_PATH = DATA_DIR / "playlist.json"
GRACE_SEC = 12.0
HOLD_SEC = 0.65
ENTER_WALK_SEC = 2.8
LEAVE_SEC = 1.65
LAST_BEAT_PAD = 1.0
DURATION_MULT = 1.08
# Recency-weighted reruns: recently aired episodes stay eligible but much less likely.
RECENCY_HALF_LIFE_SEC = 3.0 * 3600.0
RECENCY_WEIGHT_FLOOR = 0.05

_lock = threading.RLock()
_state: dict[str, Any] | None = None
_rng = random.Random()


def _packet_wav_ok(packet: dict[str, Any]) -> bool:
    beats = packet.get("beats") or []
    if len(beats) < 4:
        return False
    for beat in beats:
        audio = str(beat.get("audio") or "").strip()
        if not audio:
            return False
    return True


_HASHED_WAV = re.compile(r"^ep\d{4}_\d{2}_[a-z0-9]+_[0-9a-f]{8}\.wav$")


def packet_needs_revoice(packet: dict[str, Any]) -> bool:
    """True if any beat still uses pre-hash wav names or is missing audio."""
    beats = packet.get("beats") or []
    if not beats:
        return True
    for beat in beats:
        name = Path(str(beat.get("audio") or "")).name.lower()
        if not name or not _HASHED_WAV.match(name):
            return True
    return False


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


def _packet_id(packet: dict[str, Any]) -> str | None:
    raw = packet.get("show_episode_id", packet.get("episode_id"))
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return None


def _parse_played_at(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(int(key))] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _lookup_played(played_at: dict[str, float] | None, packet: dict[str, Any]) -> float | None:
    if not played_at:
        return None
    key = _packet_id(packet)
    if key is None:
        return None
    if key in played_at:
        try:
            return float(played_at[key])
        except (TypeError, ValueError):
            return None
    try:
        ik = int(key)
    except (TypeError, ValueError):
        return None
    if ik in played_at:
        try:
            return float(played_at[ik])
        except (TypeError, ValueError):
            return None
    return None


def _recency_weight(played_ts: float | None, now: float) -> float:
    """Full weight if never played this session; exponential recency penalty otherwise."""
    if played_ts is None:
        return 1.0
    age = max(0.0, float(now) - float(played_ts))
    # Penalty decays over a few hours; just-played stays near the floor, never zero.
    grown = 1.0 - math.exp(-age / RECENCY_HALF_LIFE_SEC)
    return RECENCY_WEIGHT_FLOOR + (1.0 - RECENCY_WEIGHT_FLOOR) * grown


def _mark_played(state: dict[str, Any], idx: int, now: float) -> None:
    packets = state.get("packets") or []
    if not packets:
        return
    key = _packet_id(packets[int(idx) % len(packets)])
    if key is None:
        return
    played = state.get("played_at")
    if not isinstance(played, dict):
        played = {}
        state["played_at"] = played
    played[key] = float(now)


def _random_index(
    packets: list[dict[str, Any]],
    avoid: int | None = None,
    played_at: dict[str, float] | None = None,
    now: float | None = None,
) -> int:
    """Recency-weighted random rerun. Prefer real episodes over the seed when both exist."""
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
    if len(pool) == 1:
        return pool[0]
    stamp = time.time() if now is None else float(now)
    weights = [_recency_weight(_lookup_played(played_at, packets[i]), stamp) for i in pool]
    return _rng.choices(pool, weights=weights, k=1)[0]


def _empty_state() -> dict[str, Any]:
    return {
        "packets": [],
        "index": 0,
        "airing": 0,
        "started_at": 0.0,
        "queued": [],
        "played_at": {},
    }


def _parse_queued(raw: Any) -> list[int]:
    if raw is None or raw is False:
        return []
    if isinstance(raw, list):
        out: list[int] = []
        for item in raw:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return []


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
            "played_at": _parse_played_at(raw.get("played_at")),
        }
        if _state["packets"]:
            _state["index"] %= len(_state["packets"])
        else:
            _state["index"] = 0
    else:
        _state = _empty_state()
    if "queued" not in _state or _state["queued"] is None:
        _state["queued"] = []
    else:
        _state["queued"] = _parse_queued(_state.get("queued"))
    if not isinstance(_state.get("played_at"), dict):
        _state["played_at"] = {}
    else:
        _state["played_at"] = _parse_played_at(_state.get("played_at"))
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
        _mark_played(state, idx, now)
        return
    limit = _duration(packets[idx]) + GRACE_SEC
    if now - started < limit:
        return
    queued = _parse_queued(state.get("queued"))
    n = len(packets)
    nxt = None
    while queued:
        cand = queued.pop(0)
        # A repeated pin of the current packet used to put the currently-airing
        # episode back at the head of its own queue. Drop that stale entry.
        if 0 <= cand < n and cand != idx:
            nxt = cand
            break
    _mark_played(state, idx, now)
    if nxt is not None:
        state["index"] = nxt
        state["queued"] = queued
    else:
        state["index"] = _random_index(
            packets,
            avoid=idx,
            played_at=state.get("played_at") or {},
            now=now,
        )
        state["queued"] = []
    state["airing"] = int(state["airing"] or 0) + 1
    state["started_at"] = now
    _mark_played(state, state["index"], now)
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
            current_idx = int(state.get("index") or 0) % len(packets)
            queued = [q for q in _parse_queued(state.get("queued")) if q != current_idx]
            if new_idx == current_idx:
                # Idempotent pin: update the stored packet, but do not schedule a
                # replay of the episode that is already on screen.
                state["queued"] = queued
                _save(state)
                try:
                    from orchestrator import archive
                    archive.upsert_episode(stored)
                except Exception:
                    pass
                return _serve_packet(state)
            if new_idx not in queued:
                queued.append(new_idx)
            state["queued"] = queued
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
        state["queued"] = []
        _mark_played(state, new_idx, now)
        _save(state)
        try:
            from orchestrator import archive
            archive.upsert_episode(stored)
        except Exception:
            pass
        return _publish(state)


def absorb(packet: dict[str, Any]) -> None:
    """Append a voiced episode to the rerun pool without interrupting now-playing."""
    if not packet or not packet.get("beats") or not _packet_wav_ok(packet):
        return
    with _lock:
        state = _load()
        stored = deepcopy(packet)
        real_id = stored.get("show_episode_id", stored.get("episode_id"))
        stored["show_episode_id"] = real_id
        packets = state["packets"]
        replaced = False
        if real_id is not None:
            for i, existing in enumerate(packets):
                if existing.get("episode_id") == real_id or existing.get("show_episode_id") == real_id:
                    packets[i] = stored
                    replaced = True
                    break
        if not replaced:
            packets.append(stored)
        _save(state)
        try:
            from orchestrator import archive
            archive.upsert_episode(stored)
        except Exception:
            pass


def _enqueue_backfill(item: dict[str, Any]) -> None:
    from orchestrator.voice_queue import LOW, submit

    scene = item.get("scene") or {}
    eid = int(item["id"])
    source = scene.get("source") or "viewer"

    def job(scene=scene, eid=eid, source=source) -> None:
        from orchestrator.tts import render

        packet = render(scene, eid)
        packet["source"] = source or packet.get("source") or "viewer"
        absorb(packet)

    submit(LOW, job)


def ensure_voiced_boot(mem) -> dict[str, Any]:
    """Restore voiced packets from manifests; backfill unvoiced on the Piper queue."""
    from copy import deepcopy as dc

    from orchestrator import archive
    from orchestrator.gemini import TOASTER_APPLICATION_SCENE
    from orchestrator.voice_queue import HIGH, start as start_queue, voice_episode

    start_queue()
    try:
        archive.init()
        try:
            mem.restore_from_archive()
        except Exception:
            pass
    except Exception:
        pass

    voiced: list[dict[str, Any]] = []
    try:
        voiced = archive.list_voiced_packets() or []
    except Exception:
        voiced = []

    if voiced:
        for pkt in voiced:
            absorb(pkt)
        published = {"episode_id": None, "scene": None, "topic": None, "beats": []}
        with _lock:
            state = _load()
            if state["packets"]:
                now = time.time()
                state["index"] = _random_index(
                    state["packets"],
                    played_at=state.get("played_at") or {},
                    now=now,
                )
                state["airing"] = max(1, int(state["airing"] or 0) + 1)
                state["started_at"] = now
                _mark_played(state, state["index"], now)
                _save(state)
                published = _publish(state)
        fresh: set[int] = set()
        for pkt in voiced:
            raw = pkt.get("show_episode_id", pkt.get("episode_id"))
            try:
                eid = int(raw)
            except (TypeError, ValueError):
                continue
            if not packet_needs_revoice(pkt):
                fresh.add(eid)
        try:
            scenes = archive.list_scenes() or []
        except Exception:
            scenes = []
        for item in reversed(list(scenes)):
            eid = item.get("id")
            scene = item.get("scene") or {}
            if eid is None or not scene.get("beats"):
                continue
            try:
                eid = int(eid)
            except (TypeError, ValueError):
                continue
            if eid in fresh:
                continue
            _enqueue_backfill(item)
        return published if published.get("beats") else current()

    scenes: list[dict[str, Any]] = []
    try:
        scenes = archive.list_scenes() or []
    except Exception:
        scenes = []
    items = [
        it
        for it in reversed(list(scenes))
        if it.get("id") is not None and (it.get("scene") or {}).get("beats")
    ]
    if items:
        first = items[0]
        scene = first.get("scene") or {}
        packet = voice_episode(
            scene,
            int(first["id"]),
            priority=HIGH,
            source=scene.get("source") or "viewer",
        )
        served = pin(packet)
        for item in items[1:]:
            _enqueue_backfill(item)
        return served

    with _lock:
        state = _load()
        if state["packets"]:
            now = time.time()
            state["index"] = _random_index(
                state["packets"],
                played_at=state.get("played_at") or {},
                now=now,
            )
            state["airing"] = max(1, int(state["airing"] or 0) + 1)
            state["started_at"] = now
            _mark_played(state, state["index"], now)
            _save(state)
            return _publish(state)

    recovered = _recover_random_from_db(mem)
    if recovered is not None:
        return pin(recovered)

    scene = dc(TOASTER_APPLICATION_SCENE)
    scene["source"] = "seed"
    episode_id = mem.insert_episode(scene.get("topic") or "seed", "seed", scene)
    packet = voice_episode(scene, episode_id, priority=HIGH, source="seed")
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
    from orchestrator.voice_queue import HIGH, voice_episode

    packet = voice_episode(scene, episode_id, priority=HIGH, source=source or "viewer")
    return packet


def remaining_seconds(now: float | None = None) -> float:
    """Seconds left on the currently airing episode, including grace."""
    now = time.time() if now is None else now
    with _lock:
        state = _load()
        _advance_if_due(state, now)
        return _remaining_locked(state, now)


def _remaining_locked(state: dict[str, Any], now: float) -> float:
    packets = state["packets"]
    if not packets:
        return 0.0
    started = float(state.get("started_at") or 0.0)
    if started <= 0:
        return 0.0
    idx = int(state.get("index") or 0) % len(packets)
    limit = _duration(packets[idx]) + GRACE_SEC
    return max(0.0, limit - (now - started))


def board() -> dict[str, Any]:
    """Now-playing title plus the paid/written upcoming queue (not the rerun pool)."""
    with _lock:
        state = _load()
        now = time.time()
        _advance_if_due(state, now)
        packets = state["packets"]
        if not packets:
            return {"now": "", "queue": []}
        idx = int(state.get("index") or 0) % len(packets)
        now_topic = str((packets[idx] or {}).get("topic") or "").strip()
        queue: list[dict[str, Any]] = []
        for qidx in _parse_queued(state.get("queued")):
            if not (0 <= qidx < len(packets)) or qidx == idx:
                continue
            pkt = packets[qidx] or {}
            topic = str(pkt.get("topic") or "").strip()
            if not topic:
                continue
            queue.append({"topic": topic, "episode_id": pkt.get("episode_id")})
        return {"now": now_topic, "queue": queue}


def queued_wait_seconds(now: float | None = None) -> float:
    """How long until a newly pinned episode would start (current remaining + queued)."""
    now = time.time() if now is None else now
    with _lock:
        state = _load()
        _advance_if_due(state, now)
        wait = _remaining_locked(state, now)
        packets = state["packets"]
        if not packets:
            return wait
        current_idx = int(state.get("index") or 0) % len(packets)
        for qidx in _parse_queued(state.get("queued")):
            if 0 <= qidx < len(packets) and qidx != current_idx:
                wait += _duration(packets[qidx]) + GRACE_SEC
        return wait


def seconds_until_episode(episode_id: int | None, now: float | None = None) -> float:
    """Seconds until the given episode starts airing. 0 if it is on now."""
    if episode_id is None:
        return queued_wait_seconds(now)
    now = time.time() if now is None else now
    with _lock:
        state = _load()
        _advance_if_due(state, now)
        packets = state["packets"]
        if not packets:
            return 0.0
        n = len(packets)
        cur = int(state.get("index") or 0) % n
        queued = _parse_queued(state.get("queued"))
        target = None
        for i, pkt in enumerate(packets):
            if pkt.get("episode_id") == episode_id or pkt.get("show_episode_id") == episode_id:
                target = i
                break
        if target is None:
            return queued_wait_seconds(now)
        # If the target is visibly airing, its ETA is now even if an old duplicate
        # queue entry survived from a prior build.
        if cur == target:
            return 0.0
        wait = _remaining_locked(state, now)
        for qidx in queued:
            if qidx == target:
                return wait
            if 0 <= qidx < n:
                wait += _duration(packets[qidx]) + GRACE_SEC
        return wait


def format_eta_copy(seconds: float) -> str:
    if seconds <= 8:
        return "on now"
    minutes = max(1, int(math.ceil(seconds / 60.0)))
    return f"Your episode airs in about {minutes}m"


def snapshot() -> dict[str, Any]:
    with _lock:
        state = _load()
        now = time.time()
        _advance_if_due(state, now)
        rem = _remaining_locked(state, now)
        return {
            "count": len(state["packets"]),
            "index": state["index"],
            "airing": state["airing"],
            "queued": _parse_queued(state.get("queued")),
            "remaining_seconds": rem,
            "topics": [p.get("topic") for p in state["packets"]],
        }
