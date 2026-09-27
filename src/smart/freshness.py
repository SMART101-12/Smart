"""Freshness checks for stored market observations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it to UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def freshness_status(
    observed_at: str,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Tell the scanner whether a stored observation is current enough.

    A record is NEVER treated as today's live data merely because it is the
    newest record. Both age and calendar date are checked.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    observed = parse_timestamp(observed_at)
    age = max(0.0, (now - observed).total_seconds())
    same_calendar_day = observed.date() == now.date()
    current = same_calendar_day and age <= max_age_seconds
    return {
        "current": current,
        "same_calendar_day": same_calendar_day,
        "age_seconds": age,
        "observed_at": observed.isoformat(),
        "checked_at": now.isoformat(),
        "reason": "fresh" if current else (
            "stale_or_previous_day" if not same_calendar_day else "stale"
        ),
    }
