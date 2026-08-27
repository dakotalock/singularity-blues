"""Prompt credits and LTM pins. Postgres blues schema in prod; SQLite locally."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

from orchestrator import DATA_DIR

BUYER_COOKIE = "sb_buyer"
OWNER_COOKIE = "sb_owner"

BUNDLES: dict[str, dict[str, Any]] = {
    "1": {
        "credits": 1,
        "pins": 0,
        "usd": 1,
        "price_env": "STRIPE_PRICE_1",
        "label": "$1 · 1 prompt",
    },
    "5": {
        "credits": 5,
        "pins": 1,
        "usd": 5,
        "price_env": "STRIPE_PRICE_5",
        "label": "$5 · 5 prompts + 1 memory pin",
    },
    "10": {
        "credits": 12,
        "pins": 1,
        "usd": 10,
        "price_env": "STRIPE_PRICE_10",
        "label": "$10 · 12 prompts + 1 memory pin",
    },
    "20": {
        "credits": 30,
        "pins": 3,
        "usd": 20,
        "price_env": "STRIPE_PRICE_20",
        "label": "$20 · 30 prompts + 3 memory pins",
    },
}

_lock = threading.RLock()
_sqlite: sqlite3.Connection | None = None


def _signing_key() -> bytes:
    for env in ("OWNER_PROMPT_SECRET", "STRIPE_WEBHOOK_SECRET", "STRIPE_SECRET_KEY"):
        val = os.environ.get(env, "").strip()
        if val:
            return val.encode("utf-8")
    return b"singularity-blues-local-credits"


def mint_buyer_id() -> str:
    return secrets.token_urlsafe(18)


def mint_recovery_key() -> str:
    return "sbk_" + secrets.token_urlsafe(16)


def sign_buyer(buyer_id: str) -> str:
    mac = hmac.new(_signing_key(), f"buyer:{buyer_id}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{buyer_id}.{mac}"


def verify_buyer(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    buyer_id, _, mac = token.partition(".")
    if not buyer_id or not mac:
        return None
    expected = hmac.new(_signing_key(), f"buyer:{buyer_id}".encode("utf-8"), hashlib.sha256).hexdigest()
    if hmac.compare_digest(mac, expected):
        return buyer_id
    return None


def owner_cookie_value() -> str | None:
    secret = os.environ.get("OWNER_PROMPT_SECRET", "").strip()
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), b"owner:ok", hashlib.sha256).hexdigest()


def is_owner(*, header: str | None = None, cookie: str | None = None) -> bool:
    secret = os.environ.get("OWNER_PROMPT_SECRET", "").strip()
    if not secret:
        return False
    if header and hmac.compare_digest(header, secret):
        return True
    expected = owner_cookie_value()
    if cookie and expected and hmac.compare_digest(cookie, expected):
        return True
    return False


def stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())


def _postgres_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def _sqlite_path() -> Path:
    override = os.environ.get("CREDITS_SQLITE_PATH", "").strip()
    if override:
        return Path(override)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "credits.db"


def _connect_pg():
    url = _postgres_url()
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


def _connect_sqlite() -> sqlite3.Connection:
    global _sqlite
    with _lock:
        if _sqlite is None:
            path = _sqlite_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS buyers (
                    id TEXT PRIMARY KEY,
                    credits INTEGER NOT NULL DEFAULT 0,
                    ltm_pins INTEGER NOT NULL DEFAULT 0,
                    recovery_key TEXT UNIQUE
                )
                """
            )
            cols = {row[1] for row in conn.execute("PRAGMA table_info(buyers)").fetchall()}
            if "recovery_key" not in cols:
                conn.execute("ALTER TABLE buyers ADD COLUMN recovery_key TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_buyers_recovery_key ON buyers(recovery_key)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stripe_events (
                    event_id TEXT PRIMARY KEY,
                    buyer_id TEXT,
                    bundle TEXT
                )
                """
            )
            conn.commit()
            _sqlite = conn
        return _sqlite


def reset_sqlite_for_tests() -> None:
    """Close the cached SQLite handle so tests can point at a fresh file."""
    global _sqlite
    with _lock:
        if _sqlite is not None:
            try:
                _sqlite.close()
            except Exception:
                pass
            _sqlite = None


def ensure_schema() -> None:
    conn = _connect_pg()
    if conn is None:
        _connect_sqlite()
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS blues")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blues.buyers (
                        id TEXT PRIMARY KEY,
                        credits INTEGER NOT NULL DEFAULT 0,
                        ltm_pins INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blues.stripe_events (
                        event_id TEXT PRIMARY KEY,
                        buyer_id TEXT,
                        bundle TEXT,
                        processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "ALTER TABLE blues.buyers ADD COLUMN IF NOT EXISTS recovery_key TEXT"
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_buyers_recovery_key
                    ON blues.buyers (recovery_key)
                    """
                )
    except Exception:
        pass
    finally:
        conn.close()


def _row_pg(buyer_id: str) -> tuple[int, int]:
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT credits, ltm_pins FROM blues.buyers WHERE id = %s",
                    (buyer_id,),
                )
                row = cur.fetchone()
                if not row:
                    return 0, 0
                return int(row[0] or 0), int(row[1] or 0)
    finally:
        conn.close()


def _add_pg(buyer_id: str, d_credits: int, d_pins: int) -> tuple[int, int]:
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO blues.buyers (id, credits, ltm_pins)
                    VALUES (%s, GREATEST(0, %s), GREATEST(0, %s))
                    ON CONFLICT (id) DO UPDATE SET
                        credits = GREATEST(0, blues.buyers.credits + %s),
                        ltm_pins = GREATEST(0, blues.buyers.ltm_pins + %s),
                        updated_at = NOW()
                    RETURNING credits, ltm_pins
                    """,
                    (buyer_id, d_credits, d_pins, d_credits, d_pins),
                )
                row = cur.fetchone()
                return int(row[0]), int(row[1])
    finally:
        conn.close()


def _event_seen_pg(event_id: str) -> bool:
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM blues.stripe_events WHERE event_id = %s",
                    (event_id,),
                )
                return cur.fetchone() is not None
    finally:
        conn.close()


def _record_event_pg(event_id: str, buyer_id: str, bundle: str) -> bool:
    """Return True if this event is newly recorded."""
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO blues.stripe_events (event_id, buyer_id, bundle)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (event_id, buyer_id, bundle),
                )
                return cur.rowcount > 0
    finally:
        conn.close()


def _row_sqlite(buyer_id: str) -> tuple[int, int]:
    conn = _connect_sqlite()
    with _lock:
        row = conn.execute(
            "SELECT credits, ltm_pins FROM buyers WHERE id = ?", (buyer_id,)
        ).fetchone()
        if not row:
            return 0, 0
        return int(row["credits"] or 0), int(row["ltm_pins"] or 0)


def _add_sqlite(buyer_id: str, d_credits: int, d_pins: int) -> tuple[int, int]:
    conn = _connect_sqlite()
    with _lock:
        row = conn.execute(
            "SELECT credits, ltm_pins FROM buyers WHERE id = ?", (buyer_id,)
        ).fetchone()
        if row:
            credits = max(0, int(row["credits"] or 0) + d_credits)
            pins = max(0, int(row["ltm_pins"] or 0) + d_pins)
            conn.execute(
                "UPDATE buyers SET credits = ?, ltm_pins = ? WHERE id = ?",
                (credits, pins, buyer_id),
            )
        else:
            credits = max(0, d_credits)
            pins = max(0, d_pins)
            conn.execute(
                "INSERT INTO buyers (id, credits, ltm_pins) VALUES (?, ?, ?)",
                (buyer_id, credits, pins),
            )
        conn.commit()
        return credits, pins


def _event_seen_sqlite(event_id: str) -> bool:
    conn = _connect_sqlite()
    with _lock:
        row = conn.execute(
            "SELECT 1 FROM stripe_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None


def _record_event_sqlite(event_id: str, buyer_id: str, bundle: str) -> bool:
    conn = _connect_sqlite()
    with _lock:
        try:
            conn.execute(
                "INSERT INTO stripe_events (event_id, buyer_id, bundle) VALUES (?, ?, ?)",
                (event_id, buyer_id, bundle),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def _use_pg() -> bool:
    return bool(_postgres_url())


def balance(buyer_id: str) -> dict[str, int]:
    if not buyer_id:
        return {"credits": 0, "ltm_pins": 0}
    try:
        if _use_pg():
            c, p = _row_pg(buyer_id)
        else:
            c, p = _row_sqlite(buyer_id)
    except Exception:
        c, p = _row_sqlite(buyer_id)
    return {"credits": c, "ltm_pins": p}


def _add(buyer_id: str, d_credits: int, d_pins: int) -> dict[str, int]:
    try:
        if _use_pg():
            c, p = _add_pg(buyer_id, d_credits, d_pins)
        else:
            c, p = _add_sqlite(buyer_id, d_credits, d_pins)
    except Exception:
        c, p = _add_sqlite(buyer_id, d_credits, d_pins)
    return {"credits": c, "ltm_pins": p}


def _get_recovery_key_pg(buyer_id: str) -> str:
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT recovery_key FROM blues.buyers WHERE id = %s",
                    (buyer_id,),
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    return ""
                return str(row[0])
    finally:
        conn.close()


def _set_recovery_key_if_empty_pg(buyer_id: str, key: str) -> str:
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT recovery_key FROM blues.buyers WHERE id = %s",
                    (buyer_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return str(row[0])
                if row:
                    cur.execute(
                        """
                        UPDATE blues.buyers
                        SET recovery_key = %s, updated_at = NOW()
                        WHERE id = %s AND (recovery_key IS NULL OR recovery_key = '')
                        """,
                        (key, buyer_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO blues.buyers (id, credits, ltm_pins, recovery_key)
                        VALUES (%s, 0, 0, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            recovery_key = COALESCE(NULLIF(blues.buyers.recovery_key, ''), EXCLUDED.recovery_key),
                            updated_at = NOW()
                        """,
                        (buyer_id, key),
                    )
                cur.execute(
                    "SELECT recovery_key FROM blues.buyers WHERE id = %s",
                    (buyer_id,),
                )
                stored = cur.fetchone()
                return str(stored[0] or "") if stored and stored[0] else key
    finally:
        conn.close()


def _lookup_recovery_pg(key: str) -> tuple[str, str] | None:
    conn = _connect_pg()
    if conn is None:
        raise RuntimeError("no postgres")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, recovery_key FROM blues.buyers WHERE recovery_key = %s",
                    (key,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return str(row[0]), str(row[1] or "")
    finally:
        conn.close()


def _get_recovery_key_sqlite(buyer_id: str) -> str:
    conn = _connect_sqlite()
    with _lock:
        row = conn.execute(
            "SELECT recovery_key FROM buyers WHERE id = ?", (buyer_id,)
        ).fetchone()
        if not row or not row["recovery_key"]:
            return ""
        return str(row["recovery_key"])


def _set_recovery_key_if_empty_sqlite(buyer_id: str, key: str) -> str:
    conn = _connect_sqlite()
    with _lock:
        row = conn.execute(
            "SELECT recovery_key FROM buyers WHERE id = ?", (buyer_id,)
        ).fetchone()
        if row and row["recovery_key"]:
            return str(row["recovery_key"])
        if row:
            conn.execute(
                """
                UPDATE buyers SET recovery_key = ?
                WHERE id = ? AND (recovery_key IS NULL OR recovery_key = '')
                """,
                (key, buyer_id),
            )
        else:
            try:
                conn.execute(
                    "INSERT INTO buyers (id, credits, ltm_pins, recovery_key) VALUES (?, 0, 0, ?)",
                    (buyer_id, key),
                )
            except sqlite3.IntegrityError:
                conn.execute(
                    """
                    UPDATE buyers SET recovery_key = ?
                    WHERE id = ? AND (recovery_key IS NULL OR recovery_key = '')
                    """,
                    (key, buyer_id),
                )
        conn.commit()
        row = conn.execute(
            "SELECT recovery_key FROM buyers WHERE id = ?", (buyer_id,)
        ).fetchone()
        if row and row["recovery_key"]:
            return str(row["recovery_key"])
        return key


def _lookup_recovery_sqlite(key: str) -> tuple[str, str] | None:
    conn = _connect_sqlite()
    with _lock:
        row = conn.execute(
            "SELECT id, recovery_key FROM buyers WHERE recovery_key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        return str(row["id"]), str(row["recovery_key"] or "")


def _get_recovery_key(buyer_id: str) -> str:
    try:
        if _use_pg():
            return _get_recovery_key_pg(buyer_id)
        return _get_recovery_key_sqlite(buyer_id)
    except Exception:
        return _get_recovery_key_sqlite(buyer_id)


def _set_recovery_key_if_empty(buyer_id: str, key: str) -> str:
    try:
        if _use_pg():
            return _set_recovery_key_if_empty_pg(buyer_id, key)
        return _set_recovery_key_if_empty_sqlite(buyer_id, key)
    except Exception:
        return _set_recovery_key_if_empty_sqlite(buyer_id, key)


def _lookup_recovery(key: str) -> tuple[str, str] | None:
    try:
        if _use_pg():
            return _lookup_recovery_pg(key)
        return _lookup_recovery_sqlite(key)
    except Exception:
        return _lookup_recovery_sqlite(key)


def ensure_recovery_key(buyer_id: str) -> str:
    if not buyer_id:
        return ""
    existing = _get_recovery_key(buyer_id)
    if existing:
        return existing
    for _ in range(5):
        key = mint_recovery_key()
        try:
            stored = _set_recovery_key_if_empty(buyer_id, key)
        except Exception:
            stored = ""
        if stored:
            return stored
        existing = _get_recovery_key(buyer_id)
        if existing:
            return existing
    return ""


def buyer_for_recovery_key(key: str) -> str | None:
    needle = (key or "").strip()
    if not needle:
        return None
    row = _lookup_recovery(needle)
    if not row:
        return None
    buyer_id, stored = row
    if not stored or len(stored) != len(needle):
        return None
    if hmac.compare_digest(stored, needle):
        return buyer_id
    return None


def grant_bundle(buyer_id: str, bundle: str, *, event_id: str | None = None) -> dict[str, Any]:
    spec = BUNDLES.get(bundle)
    if not spec or not buyer_id:
        return {"ok": False, "credits": 0, "ltm_pins": 0, "granted": False}
    if event_id:
        try:
            fresh = _record_event_pg(event_id, buyer_id, bundle) if _use_pg() else _record_event_sqlite(
                event_id, buyer_id, bundle
            )
        except Exception:
            fresh = _record_event_sqlite(event_id, buyer_id, bundle)
        if not fresh:
            bal = balance(buyer_id)
            key = ensure_recovery_key(buyer_id)
            return {"ok": True, "granted": False, "duplicate": True, "recovery_key": key, **bal}
    bal = _add(buyer_id, int(spec["credits"]), int(spec["pins"]))
    key = ensure_recovery_key(buyer_id)
    return {"ok": True, "granted": True, "bundle": bundle, "recovery_key": key, **bal}


def spend_credit(buyer_id: str, n: int = 1) -> bool:
    if n <= 0:
        return True
    bal = balance(buyer_id)
    if bal["credits"] < n:
        return False
    _add(buyer_id, -n, 0)
    return True


def refund_credit(buyer_id: str, n: int = 1) -> dict[str, int]:
    """Return a prompt credit. Never refunds Stripe money."""
    if n <= 0:
        return balance(buyer_id)
    return _add(buyer_id, n, 0)


def spend_pin(buyer_id: str, n: int = 1) -> bool:
    if n <= 0:
        return True
    bal = balance(buyer_id)
    if bal["ltm_pins"] < n:
        return False
    _add(buyer_id, 0, -n)
    return True


def refund_pin(buyer_id: str, n: int = 1) -> dict[str, int]:
    if n <= 0:
        return balance(buyer_id)
    return _add(buyer_id, 0, n)


def event_seen(event_id: str) -> bool:
    if not event_id:
        return False
    try:
        if _use_pg():
            return _event_seen_pg(event_id)
        return _event_seen_sqlite(event_id)
    except Exception:
        return _event_seen_sqlite(event_id)
