from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
CALENDAR_PATH = RUNTIME / "market_calendar.json"

EQUITY = "EQUITY"
GOLD_FUND = "GOLD_FUND"

# Explicit classification can be extended without changing the recovery engine.
# Symbols not listed here default to EQUITY.
DEFAULT_GOLD_FUND_SYMBOLS = {
    "عیار",
    "طلا",
    "گوهر",
    "مثقال",
    "زر",
    "گنج",
}

MARKET_HOURS = {
    EQUITY: {"open": "09:00", "close": "12:30"},
    GOLD_FUND: {"open": "12:00", "close": "17:00"},
}


def market_type(symbol: str) -> str:
    configured = {
        s.strip() for s in __import__("os").getenv(
            "SMART_GOLD_FUND_SYMBOLS", ",".join(sorted(DEFAULT_GOLD_FUND_SYMBOLS))
        ).split(",") if s.strip()
    }
    return GOLD_FUND if symbol.strip() in configured else EQUITY


def trading_hours(symbol: str) -> dict[str, str]:
    return MARKET_HOURS[market_type(symbol)].copy()


def _candidate_week_dates(start: date, end: date) -> set[date]:
    """Iran market weekdays: Saturday through Wednesday only."""
    out: set[date] = set()
    cur = start
    while cur <= end:
        # Python: Monday=0 ... Thursday=3, Friday=4, Saturday=5, Sunday=6.
        if cur.weekday() in (5, 6, 0, 1, 2):
            out.add(cur)
        cur += timedelta(days=1)
    return out


def _load() -> dict:
    if not CALENDAR_PATH.exists():
        return {"version": 1, "closed_dates": {EQUITY: {}, GOLD_FUND: {}}, "confirmed": {}}
    try:
        payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("closed_dates", {})
            payload.setdefault("confirmed", {})
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "closed_dates": {EQUITY: {}, GOLD_FUND: {}}, "confirmed": {}}


def _save(payload: dict) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def shared_closed_dates(kind: str) -> set[date]:
    payload = _load()
    values = payload.get("closed_dates", {}).get(kind, {})
    return {date.fromisoformat(k) for k in values if _valid_iso(k)}


def _valid_iso(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def record_closed_dates(kind: str, dates: Iterable[date], reason: str = "TSETMC") -> list[str]:
    payload = _load()
    bucket = payload.setdefault("closed_dates", {}).setdefault(kind, {})
    added: list[str] = []
    for d in sorted(set(dates)):
        key = d.isoformat()
        if key not in bucket:
            bucket[key] = {"reason": reason, "source": "market_calendar"}
            added.append(key)
    _save(payload)
    return added


def confirm_date(kind: str, d: date, decision: str, *, symbol: str | None = None) -> None:
    if decision not in {"CLOSED", "MISSING"}:
        raise ValueError("decision must be CLOSED or MISSING")
    payload = _load()
    key = d.isoformat()
    confirmed = payload.setdefault("confirmed", {}).setdefault(kind, {})
    confirmed[key] = {
        "decision": decision,
        "symbol": symbol,
    }
    if decision == "CLOSED":
        payload.setdefault("closed_dates", {}).setdefault(kind, {})[key] = {
            "reason": "USER_CONFIRMED",
            "source": "user",
        }
    _save(payload)


def is_closed_by_shared_calendar(kind: str, d: date) -> bool:
    return d in shared_closed_dates(kind)


def expected_dates(start: date, end: date, calendar_dates: set[date], kind: str) -> set[date]:
    """Return dates that should contain market data.

    Thursday/Friday are always removed. Shared exchange-closure dates are removed.
    The instrument calendar is authoritative for dates it provides.
    """
    candidates = _candidate_week_dates(start, end)
    closed = shared_closed_dates(kind)
    return {d for d in candidates if d not in closed and d in calendar_dates}


def candidate_week_dates(start: date, end: date) -> set[date]:
    return _candidate_week_dates(start, end)
