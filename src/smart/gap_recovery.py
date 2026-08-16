from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .tsetmc_adapter import TsetmcAdapter

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "smart.db"
RUNTIME = ROOT / "runtime"
HISTORY_ROOT = RUNTIME / "history"
QUALITY_ROOT = RUNTIME / "data_quality"
CALENDAR_PATH = RUNTIME / "market_calendar.json"
RETRY_SECONDS = int(os.getenv("SMART_GAP_RETRY_SECONDS", "3600"))


def _date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "").strip()
    if len(raw) != 8 or not raw.isdigit(): return None
    try: return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError: return None


def _db_dates(symbol: str, source: str = "tsetmc") -> set[date]:
    if not DB_PATH.exists(): return set()
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT market_date FROM daily_history WHERE symbol=? AND source=?", (symbol, source)).fetchall()
    return {d for x in rows if (d := _date(x[0]))}


def _load_history(symbol: str) -> dict[str, Any]:
    root = HISTORY_ROOT / symbol; rows: dict[date, dict[str, Any]] = {}; meta: dict[str, Any] = {"symbol": symbol, "source": "tsetmc"}
    if root.exists():
        for path in sorted(root.glob("*.json")):
            if not path.stem.isdigit() or len(path.stem) != 6: continue
            try: payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): continue
            if isinstance(payload, dict):
                for key in ("ins_code", "source", "symbol"):
                    if payload.get(key): meta[key] = payload[key]
                for row in payload.get("daily_history", []):
                    d = _date(row.get("dEven"))
                    if d: rows[d] = row
    flat = HISTORY_ROOT / f"{symbol}.json"
    if flat.exists():
        try: payload = json.loads(flat.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): payload = {}
        if isinstance(payload, dict):
            for key in ("ins_code", "source", "symbol"):
                if payload.get(key): meta[key] = payload[key]
            for row in payload.get("daily_history", []):
                d = _date(row.get("dEven"))
                if d: rows.setdefault(d, row)
    meta["daily_history"] = list(rows.values()); return meta


def _save_monthly(symbol: str, payload: dict[str, Any]) -> None:
    root = HISTORY_ROOT / symbol; root.mkdir(parents=True, exist_ok=True); groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("daily_history", []):
        raw = str(row.get("dEven", ""))
        if len(raw) == 8 and raw.isdigit(): groups[raw[:6]].append(row)
    for month, rows in groups.items():
        rows.sort(key=lambda r: int(r.get("dEven", 0)), reverse=True)
        out = {"symbol": symbol, "ins_code": payload.get("ins_code"), "source": payload.get("source", "tsetmc"), "month": month, "exported_at": datetime.now(timezone.utc).isoformat(), "rows": len(rows), "fields_note": "dEven=YYYYMMDD, pClosing=closing price, pDrCotVal=last/traded price, qTotTran5J=volume, qTotCap=trade value, zTotTran=trade count.", "daily_history": rows}
        (root / f"{month}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def _quality_path(symbol: str) -> Path:
    QUALITY_ROOT.mkdir(parents=True, exist_ok=True); return QUALITY_ROOT / f"{symbol}.json"


def _load_quality(symbol: str) -> dict[str, Any]:
    path = _quality_path(symbol)
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): pass
    return {"symbol": symbol, "dates": {}}


def _save_quality(symbol: str, quality: dict[str, Any]) -> None:
    quality["checked_at"] = datetime.now(timezone.utc).isoformat(); _quality_path(symbol).write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_to_git(symbol: str, payload: dict[str, Any], quality: dict[str, Any]) -> None:
    from .command_agent import put_json
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("daily_history", []):
        raw = str(row.get("dEven", ""))
        if len(raw) == 8 and raw.isdigit(): groups[raw[:6]].append(row)
    for month, rows in groups.items():
        rows.sort(key=lambda r: int(r.get("dEven", 0)), reverse=True)
        put_json(f"runtime/history/{symbol}/{month}.json", {"symbol": symbol, "ins_code": payload.get("ins_code"), "source": payload.get("source", "tsetmc"), "month": month, "exported_at": datetime.now(timezone.utc).isoformat(), "rows": len(rows), "fields_note": "dEven=YYYYMMDD, pClosing=closing price, pDrCotVal=last/traded price, qTotTran5J=volume, qTotCap=trade value, zTotTran=trade count.", "daily_history": rows}, f"agent: gap recovery {symbol} {month}")
    put_json(f"runtime/data_quality/{symbol}.json", quality, f"agent: data quality {symbol}")


def _candidate_week_dates(start: date, end: date):
    cur = start
    while cur <= end:
        if cur.weekday() in (5, 6, 0, 1, 2): yield cur
        cur += timedelta(days=1)


def _expected_dates(start: date, end: date):
    return _candidate_week_dates(start, end)


def _all_dates(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _market_type(symbol: str) -> str:
    return "GOLD_FUND" if symbol.strip() in {"عیار"} else "EQUITY"


def _official_closed_dates(symbol: str, start: date, end: date) -> set[date]:
    if not CALENDAR_PATH.exists(): return set()
    try: payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return set()
    periods = payload.get("market_types", {}).get(_market_type(symbol), {}).get("closed_periods", [])
    result: set[date] = set()
    for period in periods:
        left, right = _date(period.get("start")), _date(period.get("end"))
        if not left or not right: continue
        left, right = max(left, start), min(right, end)
        while left <= right:
            result.add(left); left += timedelta(days=1)
    return result


def _calendar_dates(adapter: TsetmcAdapter, ins_code: str) -> set[date]:
    result: set[date] = set()
    for row in adapter.instrument_calendar(ins_code):
        if isinstance(row, dict):
            d = _date(row.get("dEven") or row.get("date") or row.get("market_date"))
            if d: result.add(d)
    return result


def audit_tsetmc_history(symbol: str, *, today: date | None = None) -> dict[str, Any]:
    """Audit using TSETMC price history only; internet search is never used for prices."""
    today = today or datetime.now(timezone.utc).date(); adapter = TsetmcAdapter(); instrument = adapter.resolve_symbol(symbol); ins_code = str(instrument["insCode"])
    rows = adapter.daily_history(ins_code, 0)
    traded = {d for row in rows if isinstance(row, dict) and (d := _date(row.get("dEven")))}
    if not traded: return {"symbol": symbol, "source": "TSETMC", "status": "no_tsetmc_history"}
    start, end = min(traded), min(today - timedelta(days=1), max(traded)); candidates = set(_candidate_week_dates(start, end)); closed = _official_closed_dates(symbol, start, end)
    thursday_friday = {d for d in _all_dates(start, end) if d.weekday() in (3, 4)}
    gaps = sorted(candidates - traded - closed)
    return {"symbol": symbol, "source": "TSETMC", "ins_code": ins_code, "market_type": _market_type(symbol), "history_rows_from_tsetmc": len(rows), "range_start": start.isoformat(), "range_end": end.isoformat(), "traded_dates": len(traded), "candidate_weekdays": len(candidates), "official_closed_dates_excluded": len(closed), "thursday_friday_excluded": len(thursday_friday), "unclassified_gaps": [d.isoformat() for d in gaps], "note": "Prices/history come only from TSETMC. A TSETMC record always wins over calendar rules; calendar closures are used only when no TSETMC record exists. Thursday/Friday and known shared market closures are excluded; remaining gaps are not assumed to be holidays and must be user-reviewed."}


def repair_symbol(symbol: str, *, today: date | None = None, dry_run: bool = False) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date(); payload = _load_history(symbol); existing = {d: r for r in payload.get("daily_history", []) if (d := _date(r.get("dEven")))}; db_existing = _db_dates(symbol)
    if not existing and not db_existing: return {"symbol": symbol, "status": "no_history", "missing": []}
    start = min([*existing.keys(), *db_existing]); adapter = TsetmcAdapter(); ins_code = str(payload.get("ins_code") or "").strip()
    if not ins_code: ins_code = str(adapter.resolve_symbol(symbol)["insCode"]); payload["ins_code"] = ins_code
    calendar_dates = _calendar_dates(adapter, ins_code); scan_end = today - timedelta(days=1); candidate_dates = set(_candidate_week_dates(start, scan_end)); official_closed = _official_closed_dates(symbol, start, scan_end)
    # IMPORTANT: TSETMC history is authoritative. Calendar data must never remove or suppress a date that already has TSETMC data.
    # For missing dates, calendar closures are only an exclusion rule; all remaining candidate weekdays are checked against TSETMC.
    expected_dates = candidate_dates - official_closed
    quality = _load_quality(symbol); dates = quality.setdefault("dates", {}); stale_keys: list[str] = []
    for key, entry in list(dates.items()):
        d = _date(key)
        if d and d <= scan_end and d not in expected_dates and isinstance(entry, dict) and (entry.get("status") in {"MARKET_CLOSED_OR_NO_TRADING", "UNRESOLVED", "FETCH_FAILED"} or entry.get("retry")):
            stale_keys.append(key); dates.pop(key, None)
    repaired: list[str] = []; unresolved: list[str] = []
    for d in sorted(expected_dates):
        if d in existing or d in db_existing:
            dates.pop(d.strftime("%Y%m%d"), None)
            continue
        key = d.strftime("%Y%m%d"); entry = dates.setdefault(key, {"attempts": 0}); entry["last_check"] = datetime.now(timezone.utc).isoformat(); entry["attempts"] = int(entry.get("attempts", 0)) + 1
        try:
            row = adapter.closing_price_daily(ins_code, key)
            if isinstance(row, dict) and _date(row.get("dEven")) == d: existing[d] = row; dates.pop(key, None); repaired.append(key)
            else: entry.update({"status": "UNRESOLVED", "market_open": True, "retry": True}); unresolved.append(key)
        except Exception as exc: entry.update({"status": "FETCH_FAILED", "market_open": True, "retry": True, "error": str(exc)}); unresolved.append(key)
    payload["daily_history"] = list(existing.values()); result = {"symbol": symbol, "market_type": _market_type(symbol), "official_closed_dates_excluded": len(official_closed), "calendar_dates": len(calendar_dates), "expected_trading_dates": len(expected_dates), "stale_false_positive_dates_removed": len(stale_keys), "repaired": len(repaired), "unresolved": len(unresolved), "repaired_dates": repaired, "unresolved_dates": unresolved, "removed_false_positive_dates": stale_keys, "dry_run": dry_run}
    if not dry_run: _save_monthly(symbol, payload); quality["summary"] = result; _save_quality(symbol, quality); _sync_to_git(symbol, payload, quality)
    return result


def run(symbols: list[str]) -> None:
    while True:
        for symbol in symbols:
            try: print(f"gap-recovery {symbol}: {repair_symbol(symbol)}", flush=True)
            except Exception as exc: print(f"gap-recovery {symbol}: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(RETRY_SECONDS)
