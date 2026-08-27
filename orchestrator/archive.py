"""Durable episode library in Postgres. Dialogue survives deploys; wavs are re-voiced on boot."""

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
