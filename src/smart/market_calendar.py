"""Shared Iran-market calendar helpers.

The exchange week used by SMART is Saturday-Wednesday for the equity market.
Thursday/Friday are excluded by default. Explicit closures are persisted so a
closure learned for one symbol can be reused for all symbols in the same
market type. The calendar never infers a closure from a missing quote alone.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

EQUITY = "equity"
GOLD_FUND = "gold_fund"
ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "runtime" / "market_calendar.json"


def market_type(symbol: str) -> str:
    return GOLD_FUND if symbol in {"عیار", "طلا", "زر"} else EQUITY


def _load() -> dict:
    if PATH.exists():
        try:
            payload = json.loads(PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("closed_dates", {})
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return {"closed_dates": {EQUITY: {}, GOLD_FUND: {}}}


def _save(payload: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def candidate_week_dates(start: date, end: date) -> list[date]:
    """Return calendar candidates excluding Thursday (3) and Friday (4)."""
    if end < start:
        return []
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() not in (3, 4):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def record_closed_dates(kind: str, dates: Iterable[date], *, reason: str) -> None:
    payload = _load()
    bucket = payload.setdefault("closed_dates", {}).setdefault(kind, {})
    for d in dates:
        bucket[d.isoformat()] = {"reason": reason}
    _save(payload)


def expected_dates(
    start: date,
    end: date,
    open_dates: set[date] | None = None,
    kind: str = EQUITY,
) -> list[date]:
    candidates = candidate_week_dates(start, end)
    payload = _load()
    closed = payload.get("closed_dates", {}).get(kind, {})
    if open_dates:
        return sorted(d for d in candidates if d in open_dates and d.isoformat() not in closed)
    return sorted(d for d in candidates if d.isoformat() not in closed)
