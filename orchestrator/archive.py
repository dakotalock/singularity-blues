"""Durable episode library in Postgres. Dialogue in episodes, wavs in R2, manifests in audio_manifests."""

from __future__ import annotations

import json
import os
from typing import Any

SCHEMA = "blues"


def _url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def available() -> bool:
    return bool(_url())


def _connect():
    url = _url()
    if not url:
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        return psycopg.connect(url, connect_timeout=8)
    except Exception:
        return None


def _scene_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    beats = []
    for beat in packet.get("beats") or []:
        beats.append(
            {
                "speaker": beat.get("speaker"),
                "line": beat.get("line"),
                "emotion": beat.get("emotion") or "calm",
                "animation": beat.get("animation") or "talking",
                "target": beat.get("target"),
                "camera": beat.get("camera") or "auto",
            }
        )
    return {
        "scene": packet.get("scene") or "living_room",
        "topic": packet.get("topic") or "",
        "source": packet.get("source") or "viewer",
        "beats": beats,
    }


def init() -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        try:
            from orchestrator.credits import ensure_schema as _credits_schema
            _credits_schema()
        except Exception:
            pass
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.episodes (
                        id INTEGER PRIMARY KEY,
                        topic TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT 'viewer',
                        scene TEXT NOT NULL DEFAULT 'living_room',
                        scene_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.memories (
                        id INTEGER PRIMARY KEY,
                        character TEXT,
                        fact TEXT NOT NULL,
                        importance REAL NOT NULL DEFAULT 0.5,
                        characters JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ,
                        episode_id INTEGER
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.audio_manifests (
                        episode_id INTEGER PRIMARY KEY,
                        packet_json JSONB NOT NULL,
                        voiced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
        return True
    except Exception:
        return False
    finally:
        conn.close()


def upsert_episode(packet: dict[str, Any]) -> None:
    if not packet or not packet.get("beats"):
        return
    conn = _connect()
    if conn is None:
        return
    real_id = packet.get("show_episode_id", packet.get("episode_id"))
    try:
        eid = int(real_id)
    except (TypeError, ValueError):
        conn.close()
        return
    scene = _scene_from_packet(packet)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {SCHEMA}.episodes (id, topic, source, scene, scene_json)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        topic = EXCLUDED.topic,
                        source = EXCLUDED.source,
                        scene = EXCLUDED.scene,
                        scene_json = EXCLUDED.scene_json
                    """,
                    (
                        eid,
                        scene.get("topic") or "",
                        scene.get("source") or "viewer",
                        scene.get("scene") or "living_room",
                        json.dumps(scene),
                    ),
                )
    except Exception:
        pass
    finally:
        conn.close()


def list_scenes() -> list[dict[str, Any]]:
    """Return stored scenes as {id, source, scene} dicts. Empty if no database."""
    conn = _connect()
    if conn is None:
        return []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, source, scene_json FROM {SCHEMA}.episodes ORDER BY id ASC"
                )
                rows = cur.fetchall()
        out = []
        for eid, source, scene_json in rows:
            if isinstance(scene_json, str):
                try:
                    scene = json.loads(scene_json)
                except json.JSONDecodeError:
                    continue
            else:
                scene = scene_json or {}
            if not isinstance(scene, dict) or not scene.get("beats"):
                continue
            scene["source"] = source or scene.get("source") or "viewer"
            out.append({"id": int(eid), "scene": scene})
        return out
    except Exception:
        return []
    finally:
        conn.close()


def upsert_memories(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn = _connect()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    try:
                        mid = int(row.get("id"))
                    except (TypeError, ValueError):
                        continue
                    fact = (row.get("fact") or "").strip()
                    if not fact:
                        continue
                    chars = row.get("characters") or []
                    if isinstance(chars, str):
                        try:
                            chars = json.loads(chars)
                        except json.JSONDecodeError:
                            chars = []
                    cur.execute(
                        f"""
                        INSERT INTO {SCHEMA}.memories
                            (id, character, fact, importance, characters, created_at, episode_id)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            fact = EXCLUDED.fact,
                            importance = EXCLUDED.importance
                        """,
                        (
                            mid,
                            row.get("character"),
                            fact,
                            float(row.get("importance") or 0.5),
                            json.dumps(chars),
                            row.get("created_at"),
                            row.get("episode_id"),
                        ),
                    )
    except Exception:
        pass
    finally:
        conn.close()


def list_memories() -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, character, fact, importance, characters, created_at, episode_id
                    FROM {SCHEMA}.memories ORDER BY id ASC
                    """
                )
                rows = cur.fetchall()
        out = []
        for mid, character, fact, importance, characters, created_at, episode_id in rows:
            if isinstance(characters, str):
                try:
                    characters = json.loads(characters)
                except json.JSONDecodeError:
                    characters = []
            out.append(
                {
                    "id": int(mid),
                    "character": character,
                    "fact": fact,
                    "importance": float(importance or 0.5),
                    "characters": characters or [],
                    "created_at": str(created_at) if created_at else None,
                    "episode_id": episode_id,
                }
            )
        return out
    except Exception:
        return []
    finally:
        conn.close()


def _manifest_id(packet: dict[str, Any]) -> int | None:
    raw = packet.get("show_episode_id", packet.get("episode_id"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def upsert_manifest(packet: dict[str, Any]) -> None:
    if not packet or not packet.get("beats"):
        return
    eid = _manifest_id(packet)
    if eid is None:
        return
    conn = _connect()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {SCHEMA}.audio_manifests (episode_id, packet_json)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (episode_id) DO UPDATE SET
                        packet_json = EXCLUDED.packet_json,
                        voiced_at = NOW()
                    """,
                    (eid, json.dumps(packet)),
                )
    except Exception:
        pass
    finally:
        conn.close()


def list_voiced_packets() -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT packet_json FROM {SCHEMA}.audio_manifests ORDER BY episode_id ASC"
                )
                rows = cur.fetchall()
        out = []
        for (packet_json,) in rows:
            if isinstance(packet_json, str):
                try:
                    packet = json.loads(packet_json)
                except json.JSONDecodeError:
                    continue
            else:
                packet = packet_json or {}
            if not isinstance(packet, dict) or not packet.get("beats"):
                continue
            out.append(packet)
        return out
    except Exception:
        return []
    finally:
        conn.close()


def voiced_ids() -> set[int]:
    conn = _connect()
    if conn is None:
        return set()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT episode_id FROM {SCHEMA}.audio_manifests")
                rows = cur.fetchall()
        out: set[int] = set()
        for row in rows:
            try:
                out.add(int(row[0]))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return set()
    finally:
        conn.close()

# Advisory lock key for allocating blues episode ids (stable across processes).
_EPISODE_ID_LOCK = 834021001


def next_episode_id() -> int | None:
    """Allocate a durable episode id from Postgres.

    Returns MAX(id) across blues.episodes AND blues.audio_manifests, plus 1.
    Holds a transaction advisory lock and inserts a placeholder row so concurrent
    callers cannot reuse the same id. Returns None if the archive is unavailable
    (caller should fall back to sqlite autoincrement).
    """
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (_EPISODE_ID_LOCK,))
                cur.execute(
                    f"""
                    SELECT GREATEST(
                        COALESCE((SELECT MAX(id) FROM {SCHEMA}.episodes), 0),
                        COALESCE((SELECT MAX(episode_id) FROM {SCHEMA}.audio_manifests), 0)
                    )
                    """
                )
                row = cur.fetchone()
                nxt = int((row[0] if row else 0) or 0) + 1
                cur.execute(
                    f"""
                    INSERT INTO {SCHEMA}.episodes (id, topic, source, scene, scene_json)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (nxt, "", "pending", "living_room", "{}"),
                )
        return nxt
    except Exception:
        return None
    finally:
        conn.close()
