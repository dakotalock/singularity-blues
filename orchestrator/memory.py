"""SQLite + FTS5 show memory. retrieve() for the writer, commit() for the condenser."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from orchestrator import DATA_DIR, DB_PATH
from orchestrator.schemas import Condensation

_FTS_TOKEN = re.compile(r"[A-Za-z0-9]{3,}")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    voice_notes TEXT,
    bio TEXT
);

CREATE TABLE IF NOT EXISTS relationships (
    a TEXT NOT NULL,
    b TEXT NOT NULL,
    trust REAL NOT NULL DEFAULT 0.5,
    tension REAL NOT NULL DEFAULT 0.0,
    notes TEXT,
    PRIMARY KEY (a, b)
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character TEXT,
    fact TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    characters TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    episode_id INTEGER,
    resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    source TEXT,
    scene TEXT,
    scene_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS running_gags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gag TEXT NOT NULL UNIQUE,
    count INTEGER NOT NULL DEFAULT 1,
    last_episode_id INTEGER,
    resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS viewer_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rejection_reason TEXT
);

CREATE TABLE IF NOT EXISTS world_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS character_preferences (
    character TEXT NOT NULL,
    key TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (character, key)
);
"""


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _fts_match_query(topic: str) -> str:
    tokens = _FTS_TOKEN.findall(topic or "")
    if not tokens:
        return ""
    # Quote tokens so FTS5 treats them as literals, join with OR for recall.
    return " OR ".join('"' + t.replace('"', "") + '"' for t in tokens[:12])


class Memory:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self._ensure_fts()
            self.conn.commit()

    def _ensure_fts(self) -> None:
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
        ).fetchone()
        if row:
            return
        self.conn.execute(
            "CREATE VIRTUAL TABLE memories_fts USING fts5(fact, content='memories', content_rowid='id')"
        )
        self.conn.execute(
            """
            CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
              INSERT INTO memories_fts(rowid, fact) VALUES (new.id, new.fact);
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
              INSERT INTO memories_fts(memories_fts, rowid, fact) VALUES('delete', old.id, old.fact);
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
              INSERT INTO memories_fts(memories_fts, rowid, fact) VALUES('delete', old.id, old.fact);
              INSERT INTO memories_fts(rowid, fact) VALUES (new.id, new.fact);
            END
            """
        )
        # Backfill if memories already existed.
        existing = self.conn.execute("SELECT id, fact FROM memories").fetchall()
        for mem in existing:
            self.conn.execute(
                "INSERT INTO memories_fts(rowid, fact) VALUES (?, ?)",
                (mem["id"], mem["fact"]),
            )

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _rows(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        cur = self.conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    # --- viewer queue ---

    def enqueue_prompt(self, text: str, status: str = "pending", reason: str | None = None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO viewer_prompts (text, status, rejection_reason) VALUES (?, ?, ?)",
                (text, status, reason),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def pending_prompts(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return self._rows(
                "SELECT id, text, status, created_at FROM viewer_prompts "
                "WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            )

    def recent_prompt_texts(self, limit: int = 40) -> list[str]:
        with self._lock:
            rows = self._rows(
                "SELECT text FROM viewer_prompts ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [r["text"] for r in rows]

    def mark_prompts(self, ids: list[int], status: str, reason: str | None = None) -> None:
        if not ids:
            return
        with self._lock:
            for pid in ids:
                self.conn.execute(
                    "UPDATE viewer_prompts SET status = ?, rejection_reason = ? WHERE id = ?",
                    (status, reason, pid),
                )
            self.conn.commit()

    # --- characters / world ---

    def upsert_character(self, id: str, name: str, role: str, voice_notes: str, bio: str) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO characters (id, name, role, voice_notes, bio)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, role=excluded.role,
                    voice_notes=excluded.voice_notes, bio=excluded.bio
                """,
                (id, name, role, voice_notes, bio),
            )
            self.conn.commit()

    def list_characters(self) -> list[dict[str, Any]]:
        with self._lock:
            chars = self._rows("SELECT * FROM characters ORDER BY id")
            prefs = self._rows("SELECT * FROM character_preferences")
            by_c: dict[str, dict[str, float]] = {}
            for p in prefs:
                by_c.setdefault(p["character"], {})[p["key"]] = p["value"]
            for c in chars:
                c["preferences"] = by_c.get(c["id"], {})
            return chars

    def set_preference(self, character: str, key: str, value: float) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO character_preferences (character, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(character, key) DO UPDATE SET value=excluded.value
                """,
                (character, key, _clamp(value)),
            )
            self.conn.commit()

    def set_relationship(
        self, a: str, b: str, trust: float = 0.5, tension: float = 0.0, notes: str = ""
    ) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO relationships (a, b, trust, tension, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(a, b) DO UPDATE SET
                    trust=excluded.trust, tension=excluded.tension, notes=excluded.notes
                """,
                (a, b, _clamp(trust), _clamp(tension), notes),
            )
            self.conn.commit()

    def set_world(self, key: str, value: Any) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO world_state (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
                """,
                (key, value if isinstance(value, str) else json.dumps(value)),
            )
            self.conn.commit()

    def get_world(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM world_state WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def add_memory(
        self,
        fact: str,
        *,
        character: str | None = None,
        importance: float = 0.5,
        characters: list[str] | None = None,
        episode_id: int | None = None,
    ) -> int:
        with self._lock:
            cur = self.conn.execute(
                """
                INSERT INTO memories (character, fact, importance, characters, episode_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    character,
                    fact,
                    _clamp(importance),
                    json.dumps(characters or ([character] if character else [])),
                    episode_id,
                ),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def add_running_gag(self, gag: str, episode_id: int | None = None) -> None:
        with self._lock:
            existing = self.conn.execute(
                "SELECT id, count FROM running_gags WHERE gag = ?", (gag,)
            ).fetchone()
            if existing:
                self.conn.execute(
                    "UPDATE running_gags SET count = count + 1, last_episode_id = ?, resolved = 0 WHERE id = ?",
                    (episode_id, existing["id"]),
                )
            else:
                self.conn.execute(
                    "INSERT INTO running_gags (gag, count, last_episode_id) VALUES (?, 1, ?)",
                    (gag, episode_id),
                )
            self.conn.commit()

    def insert_episode(self, topic: str, source: str, scene: dict[str, Any]) -> int:
        with self._lock:
            cur = self.conn.execute(
                """
                INSERT INTO episodes (topic, source, scene, scene_json)
                VALUES (?, ?, ?, ?)
                """,
                (topic, source, scene.get("scene"), json.dumps(scene)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def list_episodes(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._rows(
                "SELECT id, topic, source, scene, created_at FROM episodes ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return rows

    def list_memories(self, limit: int = 40, unresolved_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT * FROM memories"
            if unresolved_only:
                sql += " WHERE resolved = 0"
            sql += " ORDER BY importance DESC, id DESC LIMIT ?"
            rows = self._rows(sql, (limit,))
            for r in rows:
                try:
                    r["characters"] = json.loads(r["characters"] or "[]")
                except json.JSONDecodeError:
                    r["characters"] = []
            return rows

    def retrieve(self, topic: str, limit: int = 12) -> dict[str, Any]:
        """Pull FTS hits, high-importance memories, prefs, gags, world, recent episodes."""
        with self._lock:
            fts_hits: list[dict[str, Any]] = []
            match = _fts_match_query(topic)
            if match:
                try:
                    fts_hits = self._rows(
                        """
                        SELECT m.* FROM memories_fts f
                        JOIN memories m ON m.id = f.rowid
                        WHERE memories_fts MATCH ? AND m.resolved = 0
                        ORDER BY bm25(memories_fts) ASC
                        LIMIT ?
                        """,
                        (match, limit),
                    )
                except sqlite3.OperationalError:
                    fts_hits = []

            important = self._rows(
                "SELECT * FROM memories WHERE resolved = 0 ORDER BY importance DESC, id DESC LIMIT 8"
            )
            seen: set[int] = set()
            merged: list[dict[str, Any]] = []
            for row in fts_hits + important:
                if row["id"] in seen:
                    continue
                seen.add(row["id"])
                try:
                    row["characters"] = json.loads(row["characters"] or "[]")
                except json.JSONDecodeError:
                    row["characters"] = []
                merged.append(row)

            prefs = self._rows("SELECT * FROM character_preferences ORDER BY character, key")
            gags = self._rows(
                "SELECT gag, count, last_episode_id FROM running_gags WHERE resolved = 0 ORDER BY count DESC"
            )
            world = {r["key"]: r["value"] for r in self._rows("SELECT key, value FROM world_state")}
            recent = self._rows(
                "SELECT id, topic, source, created_at FROM episodes ORDER BY id DESC LIMIT 8"
            )
            rels = self._rows("SELECT * FROM relationships")
            chars = self._rows("SELECT id, name, role, voice_notes, bio FROM characters ORDER BY id")
            return {
                "topic": topic,
                "memories": merged[:limit],
                "preferences": prefs,
                "running_gags": gags,
                "world_state": world,
                "recent_episodes": recent,
                "relationships": rels,
                "characters": chars,
            }

    def commit(self, condensation: Condensation | dict[str, Any], episode_id: int | None = None) -> None:
        """Apply condenser output: memories, relationship deltas, bounded prefs, gags, resolutions."""
        if isinstance(condensation, dict):
            condensation = Condensation.model_validate(condensation)
        with self._lock:
            for mem in condensation.new_memories:
                self.conn.execute(
                    """
                    INSERT INTO memories (character, fact, importance, characters, episode_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        mem.character,
                        mem.fact,
                        _clamp(mem.importance),
                        json.dumps(mem.characters or ([mem.character] if mem.character else [])),
                        episode_id,
                    ),
                )
            for rel in condensation.relationship_changes:
                row = self.conn.execute(
                    "SELECT trust, tension FROM relationships WHERE a = ? AND b = ?",
                    (rel.a, rel.b),
                ).fetchone()
                if row:
                    trust = _clamp(row["trust"] + rel.delta_trust)
                    tension = _clamp(row["tension"] + rel.delta_tension)
                    self.conn.execute(
                        "UPDATE relationships SET trust = ?, tension = ? WHERE a = ? AND b = ?",
                        (trust, tension, rel.a, rel.b),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO relationships (a, b, trust, tension) VALUES (?, ?, ?, ?)",
                        (rel.a, rel.b, _clamp(0.5 + rel.delta_trust), _clamp(rel.delta_tension)),
                    )
            for pref in condensation.preference_deltas:
                row = self.conn.execute(
                    "SELECT value FROM character_preferences WHERE character = ? AND key = ?",
                    (pref.character, pref.key),
                ).fetchone()
                current = row["value"] if row else 0.5
                new_val = _clamp(current + pref.delta)
                self.conn.execute(
                    """
                    INSERT INTO character_preferences (character, key, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(character, key) DO UPDATE SET value=excluded.value
                    """,
                    (pref.character, pref.key, new_val),
                )
            for gag in condensation.new_running_gags:
                if not gag:
                    continue
                existing = self.conn.execute(
                    "SELECT id FROM running_gags WHERE gag = ?", (gag,)
                ).fetchone()
                if existing:
                    self.conn.execute(
                        "UPDATE running_gags SET count = count + 1, last_episode_id = ?, resolved = 0 WHERE id = ?",
                        (episode_id, existing["id"]),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO running_gags (gag, count, last_episode_id) VALUES (?, 1, ?)",
                        (gag, episode_id),
                    )
            for thread in condensation.resolved_threads:
                if not thread:
                    continue
                self.conn.execute(
                    "UPDATE memories SET resolved = 1 WHERE fact LIKE ? AND resolved = 0",
                    (f"%{thread}%",),
                )
                self.conn.execute(
                    "UPDATE running_gags SET resolved = 1 WHERE gag LIKE ?",
                    (f"%{thread}%",),
                )
            self.conn.commit()
