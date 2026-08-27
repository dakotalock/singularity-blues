"""America/Denver spoken stamps for Maris's archive."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")


def _ordinal(day: int) -> str:
    if 11 <= (day % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def denver_logged_at(value: Any) -> str:
    """UTC created_at (naive SQLite or aware Postgres) as spoken Denver time.

    Example: 2026-08-27 05:07:48Z -> 'Wednesday, August 26th, 11:07 PM Denver'
    """
    utc = _parse_utc(value)
    if utc is None:
        return ""
    local = utc.astimezone(DENVER)
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return (
        f"{local.strftime('%A')}, {local.strftime('%B')} {_ordinal(local.day)}, "
        f"{hour12}:{local.strftime('%M')} {ampm} Denver"
    )
