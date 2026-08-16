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
HISTORY_DIR = RUNTIME / "history"
QUALITY_DIR = RUNTIME / "data_quality"
RETRY_SECONDS = int(os.getenv("SMART_GAP_RETRY_SECONDS", "3600"))
MAX_ATTEMPTS = int(os.getenv("SMART_GAP_MAX_ATTEMPTS", "0"))


def _date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _db_dates(symbol: str, source: str = "tsetmc") -> list[str]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT market_date FROM daily_history WHERE symbol=? AND source=? ORDER BY market_date", (symbol, source)).fetchall()
    return [str(r[0]).replace("-", "") for r in rows if r[0]]


def _load_history(symbol: str) -> dict[str, Any]:
    path = HISTORY_DIR / f"{symbol}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"symbol": symbol, "daily_history": []}


def _save_history(symbol: str, payload: dict[str, Any]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    rows = payload.get("daily_history", [])
    payload["daily_history"] = sorted(rows, key=lambda r: int(r.get("dEven", 0)), reverse=True)
    payload["history_rows"] = len(rows)
    payload["first_history_date"] = payload["daily_history"][-1].get("dEven") if rows else None
    payload["last_history_date"] = payload["daily_history"][0].get("dEven") if rows else None
    payload["repaired_at"] = datetime.now(timezone.utc).isoformat()
    (HISTORY_DIR / f"{symbol}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _quality_path(symbol: str) -> Path:
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    return QUALITY_DIR / f"{symbol}.json"


def _load_quality(symbol: str) -> dict[str, Any]:
    path = _quality_path(symbol)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"symbol": symbol, "dates": {}}


def _save_quality(symbol: str, quality: dict[str, Any]) -> None:
    quality["checked_at"] = datetime.now(timezone.utc).isoformat()
    _quality_path(symbol).write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


def _expected_dates(start: date, end: date):
    # Tehran exchange candidate trading days: Saturday through Wednesday.
    cur = start
    while cur <= end:
        if cur.weekday() in (5, 6, 0, 1, 2):
            yield cur
        cur += timedelta(days=1)


def _monthly_lookup_payloads(symbol: str, history_payload: dict[str, Any]):
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fields = ("dEven", "pClosing", "pDrCotVal", "priceFirst", "priceMin", "priceMax", "priceYesterday", "priceChange", "zTotTran", "qTotTran5J", "qTotCap", "iClose", "yClose", "last", "hEven")
    for row in history_payload.get("daily_history", []):
        raw = str(row.get("dEven", ""))
        if len(raw) == 8 and raw.isdigit():
            groups[raw[:6]].append({k: row.get(k) for k in fields if k in row})
    return {m: {"symbol": symbol, "ins_code": history_payload.get("ins_code"), "source": history_payload.get("source", "tsetmc"), "month": m, "updated_at": history_payload.get("repaired_at"), "rows": len(rs), "daily": sorted(rs, key=lambda r: int(r.get("dEven", 0)), reverse=True)} for m, rs in groups.items()}


def _sync_to_git(symbol: str, history_payload: dict[str, Any], quality: dict[str, Any]) -> None:
    from .command_agent import put_json
    put_json(f"runtime/history/{symbol}.json", history_payload, f"agent: gap recovery {symbol}")
    put_json(f"runtime/data_quality/{symbol}.json", quality, f"agent: data quality {symbol}")
    for month, payload in _monthly_lookup_payloads(symbol, history_payload).items():
        put_json(f"runtime/history_lookup/{symbol}/{month}.json", payload, f"agent: gap recovery lookup {symbol} {month}")


def repair_symbol(symbol: str, *, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    db_dates = _db_dates(symbol)
    history_payload = _load_history(symbol)
    rows = history_payload.get("daily_history", [])
    existing: dict[date, dict[str, Any]] = {}
    for row in rows:
        d = _date(row.get("dEven"))
        if d:
            existing[d] = row
    # SQLite is authoritative locally; merge any DB dates into the coverage set.
    db_parsed = [_date(d) for d in db_dates]
    db_parsed = [d for d in db_parsed if d]
    if not existing and not db_parsed:
        result = {"symbol": symbol, "status": "no_history", "missing": []}
        _save_quality(symbol, result)
        return result
    start = min([*existing.keys(), *db_parsed])
    quality = _load_quality(symbol)
    dates = quality.setdefault("dates", {})
    missing = [d for d in _expected_dates(start, today) if d not in existing and d not in db_parsed]
    ins_code = str(history_payload.get("ins_code", "")).strip()
    if not ins_code:
        result = {"symbol": symbol, "status": "missing_ins_code", "missing": [d.strftime("%Y%m%d") for d in missing]}
        _save_quality(symbol, result)
        return result
    source_rows = TsetmcAdapter().daily_history(ins_code, 0)
    source_by_date = {d: row for row in source_rows if (d := _date(row.get("dEven")))}
    repaired, unresolved = [], []
    for d in missing:
        key = d.strftime("%Y%m%d")
        entry = dates.setdefault(key, {"attempts": 0})
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        entry["last_check"] = datetime.now(timezone.utc).isoformat()
        row = source_by_date.get(d)
        if row:
            existing[d] = row
            entry.update({"status": "DATA_AVAILABLE", "market_open": True, "retry": False})
            repaired.append(key)
        else:
            entry.update({"status": "UNRESOLVED", "market_open": "unknown", "retry": True})
            unresolved.append(key)
    history_payload["daily_history"] = list(existing.values())
    _save_history(symbol, history_payload)
    quality["summary"] = {"missing_before": len(missing), "repaired": len(repaired), "unresolved": len(unresolved), "next_retry_seconds": RETRY_SECONDS}
    _save_quality(symbol, quality)
    _sync_to_git(symbol, history_payload, quality)
    return {"symbol": symbol, **quality["summary"], "repaired_dates": repaired, "unresolved_dates": unresolved}


def run(symbols: list[str]) -> None:
    while True:
        for symbol in symbols:
            try:
                print(f"gap-recovery {symbol}: {repair_symbol(symbol)}", flush=True)
            except Exception as exc:
                print(f"gap-recovery {symbol}: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(RETRY_SECONDS)
