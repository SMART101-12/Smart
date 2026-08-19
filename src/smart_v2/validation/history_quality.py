from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HISTORY_ROOT = ROOT / "runtime" / "history"
CALENDAR_PATH = ROOT / "runtime" / "market_calendar.json"
WEEKLY_CLOSED_WEEKDAYS = {3, 4}  # Thursday, Friday


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_symbol_rows(symbol: str) -> dict[date, dict[str, Any]]:
    root = HISTORY_ROOT / symbol
    rows: dict[date, dict[str, Any]] = {}
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.json")):
        if len(path.stem) != 6 or not path.stem.isdigit():
            continue
        payload = _load_json(path)
        for row in payload.get("daily_history", []):
            if not isinstance(row, dict):
                continue
            d = _parse_date(row.get("dEven"))
            if d:
                rows[d] = row
    return rows


def _closed_dates(start: date, end: date, market_type: str = "EQUITY") -> set[date]:
    payload = _load_json(CALENDAR_PATH)
    periods = payload.get("market_types", {}).get(market_type, {}).get("closed_periods", [])
    result: set[date] = set()
    for period in periods:
        left = _parse_date(period.get("start"))
        right = _parse_date(period.get("end"))
        if not left or not right or right < start or left > end:
            continue
        left, right = max(left, start), min(right, end)
        while left <= right:
            result.add(left)
            left += timedelta(days=1)
    return result


def _candidate_dates(start: date, end: date) -> set[date]:
    out: set[date] = set()
    cur = start
    while cur <= end:
        if cur.weekday() not in WEEKLY_CLOSED_WEEKDAYS:
            out.add(cur)
        cur += timedelta(days=1)
    return out


def audit_symbol(symbol: str, *, start: date | None = None, end: date | None = None, market_type: str = "EQUITY") -> dict[str, Any]:
    rows = load_symbol_rows(symbol)
    if not rows:
        return {"symbol": symbol, "status": "NO_DATA"}
    start = start or min(rows)
    end = end or max(rows)
    closed = _closed_dates(start, end, market_type)
    candidates = _candidate_dates(start, end)
    expected = candidates - closed
    present = {d for d in rows if start <= d <= end}
    zero_trade = {d for d in present if float(rows[d].get("zTotTran", 0) or 0) == 0}
    missing = sorted(expected - present)
    weekly_closed = sorted(d for d in _date_range(start, end) if d.weekday() in WEEKLY_CLOSED_WEEKDAYS)
    official_closed = sorted(d for d in closed if d.weekday() not in WEEKLY_CLOSED_WEEKDAYS)
    return {
        "symbol": symbol,
        "status": "OK" if not missing else "GAP_DETECTED",
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "rows": len(rows),
        "present_dates": len(present),
        "candidate_dates": len(candidates),
        "closed_dates_excluded": len(closed),
        "weekly_closed_excluded": len(weekly_closed),
        "expected_trading_dates": len(expected),
        "missing_expected": [d.isoformat() for d in missing],
        "zero_trade_records": [d.isoformat() for d in sorted(zero_trade)],
        "classification": {
            "DATA_PRESENT": len(present),
            "MISSING_EXPECTED": len(missing),
            "WEEKLY_CLOSED": len(weekly_closed),
            "OFFICIAL_CLOSED": len(official_closed),
            "ZERO_TRADE_RECORD": len(zero_trade),
        },
    }


def _date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)
