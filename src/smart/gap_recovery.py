from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .market_calendar import (
    EQUITY,
    candidate_week_dates,
    expected_dates as calendar_expected_dates,
    market_type,
    record_closed_dates,
)
from .tsetmc_adapter import TsetmcAdapter

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "smart.db"
RUNTIME = ROOT / "runtime"
HISTORY_ROOT = RUNTIME / "history"
QUALITY_ROOT = RUNTIME / "data_quality"
RETRY_SECONDS = int(os.getenv("SMART_GAP_RETRY_SECONDS", "3600"))


def _date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _db_dates(symbol: str, source: str = "tsetmc") -> set[date]:
    if not DB_PATH.exists():
        return set()
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT market_date FROM daily_history WHERE symbol=? AND source=?",
            (symbol, source),
        ).fetchall()
    return {d for x in rows if (d := _date(x[0]))}


def _load_history(symbol: str) -> dict[str, Any]:
    """Load canonical Git history from runtime/history/<symbol>/<YYYYMM>.json."""
    root = HISTORY_ROOT / symbol
    rows: dict[date, dict[str, Any]] = {}
    meta: dict[str, Any] = {"symbol": symbol, "source": "tsetmc"}
    if root.exists():
        for path in sorted(root.glob("*.json")):
            if not path.stem.isdigit() or len(path.stem) != 6:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                for key in ("ins_code", "source", "symbol"):
                    if payload.get(key):
                        meta[key] = payload[key]
                for row in payload.get("daily_history", []):
                    d = _date(row.get("dEven"))
                    if d:
                        rows[d] = row
    flat = HISTORY_ROOT / f"{symbol}.json"
    if flat.exists():
        try:
            payload = json.loads(flat.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for key in ("ins_code", "source", "symbol"):
                    if payload.get(key):
                        meta[key] = payload[key]
                for row in payload.get("daily_history", []):
                    d = _date(row.get("dEven"))
                    if d:
                        rows.setdefault(d, row)
        except (OSError, json.JSONDecodeError):
            pass
    meta["daily_history"] = list(rows.values())
    return meta


def _save_monthly(symbol: str, payload: dict[str, Any]) -> None:
    root = HISTORY_ROOT / symbol
    root.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("daily_history", []):
        raw = str(row.get("dEven", ""))
        if len(raw) == 8 and raw.isdigit():
            groups[raw[:6]].append(row)
    for month, rows in groups.items():
        rows.sort(key=lambda r: int(r.get("dEven", 0)), reverse=True)
        out = {
            "symbol": symbol,
            "ins_code": payload.get("ins_code"),
            "source": payload.get("source", "tsetmc"),
            "month": month,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "rows": len(rows),
            "fields_note": "dEven=YYYYMMDD, pClosing=closing price, pDrCotVal=last/traded price, qTotTran5J=volume, qTotCap=trade value, zTotTran=trade count.",
            "daily_history": rows,
        }
        (root / f"{month}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _quality_path(symbol: str) -> Path:
    QUALITY_ROOT.mkdir(parents=True, exist_ok=True)
    return QUALITY_ROOT / f"{symbol}.json"


def _load_quality(symbol: str) -> dict[str, Any]:
    path = _quality_path(symbol)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"symbol": symbol, "dates": {}}


def _save_quality(symbol: str, quality: dict[str, Any]) -> None:
    quality["checked_at"] = datetime.now(timezone.utc).isoformat()
    _quality_path(symbol).write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _sync_to_git(symbol: str, payload: dict[str, Any], quality: dict[str, Any]) -> None:
    """Write repaired history and data-quality state back to Git."""
    from .command_agent import put_json

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("daily_history", []):
        raw = str(row.get("dEven", ""))
        if len(raw) == 8 and raw.isdigit():
            groups[raw[:6]].append(row)
    for month, rows in groups.items():
        rows.sort(key=lambda r: int(r.get("dEven", 0)), reverse=True)
        month_payload = {
            "symbol": symbol,
            "ins_code": payload.get("ins_code"),
            "source": payload.get("source", "tsetmc"),
            "month": month,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "rows": len(rows),
            "fields_note": "dEven=YYYYMMDD, pClosing=closing price, pDrCotVal=last/traded price, qTotTran5J=volume, qTotCap=trade value, zTotTran=trade count.",
            "daily_history": rows,
        }
        put_json(
            f"runtime/history/{symbol}/{month}.json",
            month_payload,
            f"agent: gap recovery {symbol} {month}",
        )
    put_json(f"runtime/data_quality/{symbol}.json", quality, f"agent: data quality {symbol}")


def _calendar_dates(adapter: TsetmcAdapter, ins_code: str) -> tuple[set[date], set[date]]:
    """Return (open dates, explicitly closed dates) from TSETMC calendar.

    TSETMC response fields vary by endpoint version, so closure flags are
    recognized conservatively. A date is never declared closed merely because
    it is absent from the calendar.
    """
    rows = adapter.instrument_calendar(ins_code)
    open_dates: set[date] = set()
    closed_dates: set[date] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = _date(row.get("dEven") or row.get("date") or row.get("market_date"))
        if not d:
            continue
        raw = " ".join(str(row.get(k, "")).lower() for k in (
            "status", "state", "description", "desc", "title", "reason", "type", "isOpen"
        ))
        false_flag = any(row.get(k) is False for k in ("isOpen", "open", "isTrading", "trading"))
        closed_word = any(x in raw for x in ("closed", "holiday", "تعطیل", "غیر معاملاتی", "no trading"))
        if false_flag or closed_word:
            closed_dates.add(d)
        else:
            open_dates.add(d)
    return open_dates, closed_dates


def _expected_dates(start: date, end: date, calendar_dates: set[date] | None = None) -> list[date]:
    """Backward-compatible weekday filter used by tests and callers."""
    candidates = candidate_week_dates(start, end)
    if calendar_dates is None:
        return sorted(candidates)
    return sorted(d for d in candidates if d in calendar_dates)


def repair_symbol(symbol: str, *, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    payload = _load_history(symbol)
    existing = {
        d: r
        for r in payload.get("daily_history", [])
        if (d := _date(r.get("dEven")))
    }
    db_existing = _db_dates(symbol)

    if not existing and not db_existing:
        result = {"symbol": symbol, "status": "no_history", "missing": []}
        _save_quality(symbol, result)
        return result

    start = min([*existing.keys(), *db_existing])
    adapter = TsetmcAdapter()
    ins_code = str(payload.get("ins_code") or "").strip()
    if not ins_code:
        ins_code = str(adapter.resolve_symbol(symbol)["insCode"])
        payload["ins_code"] = ins_code

    kind = market_type(symbol)
    calendar_open, calendar_closed = _calendar_dates(adapter, ins_code)
    # Explicit exchange closures are shared across all instruments of the same
    # market type. We do not infer closure from an absent calendar row.
    if calendar_closed:
        record_closed_dates(kind, calendar_closed, reason="TSETMC_MARKET_CALENDAR")

    scan_end = today - timedelta(days=1)
    expected_dates = calendar_expected_dates(start, scan_end, calendar_open, kind)

    quality = _load_quality(symbol)
    dates = quality.setdefault("dates", {})

    # Remove stale retry/missing records that are now known to be weekends or
    # confirmed market-closure dates. Never delete a user-confirmed real gap.
    stale_keys: list[str] = []
    for key, entry in list(dates.items()):
        d = _date(key)
        if not d or d > scan_end or not isinstance(entry, dict):
            continue
        if d not in expected_dates and entry.get("status") in {
            "MARKET_CLOSED_OR_NO_TRADING", "UNRESOLVED", "FETCH_FAILED"
        }:
            stale_keys.append(key)
            dates.pop(key, None)

    repaired: list[str] = []
    unresolved: list[str] = []

    for d in sorted(expected_dates):
        if d in existing or d in db_existing:
            dates.pop(d.strftime("%Y%m%d"), None)
            continue

        key = d.strftime("%Y%m%d")
        entry = dates.setdefault(key, {"attempts": 0})
        entry["last_check"] = datetime.now(timezone.utc).isoformat()
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        try:
            row = adapter.closing_price_daily(ins_code, key)
            if isinstance(row, dict) and _date(row.get("dEven")) == d:
                existing[d] = row
                dates.pop(key, None)
                repaired.append(key)
            else:
                entry.update({"status": "NEEDS_USER_REVIEW", "market_open": True, "retry": False})
                unresolved.append(key)
        except Exception as exc:
            entry.update({
                "status": "FETCH_FAILED",
                "market_open": True,
                "retry": True,
                "error": str(exc),
            })
            unresolved.append(key)

    payload["daily_history"] = list(existing.values())
    _save_monthly(symbol, payload)
    quality["summary"] = {
        "market_type": kind,
        "history_layout": "runtime/history/<symbol>/<YYYYMM>.json",
        "calendar_open_dates": len(calendar_open),
        "calendar_closed_dates": len(calendar_closed),
        "expected_trading_dates": len(expected_dates),
        "stale_false_positive_dates_removed": len(stale_keys),
        "repaired": len(repaired),
        "needs_user_review": len(unresolved),
        "next_retry_seconds": RETRY_SECONDS,
    }
    _save_quality(symbol, quality)
    _sync_to_git(symbol, payload, quality)

    return {
        "symbol": symbol,
        **quality["summary"],
        "repaired_dates": repaired,
        "unresolved_dates": unresolved,
        "removed_false_positive_dates": stale_keys,
    }


def run(symbols: list[str]) -> None:
    while True:
        for symbol in symbols:
            try:
                print(f"gap-recovery {symbol}: {repair_symbol(symbol)}", flush=True)
            except Exception as exc:
                print(f"gap-recovery {symbol}: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(RETRY_SECONDS)
