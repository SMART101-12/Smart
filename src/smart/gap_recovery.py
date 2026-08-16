"""Historical data gap detection and retry engine for SMART.

The engine scans every calendar day in the stored history range, checks the
market-data source for missing trading records, persists a data-quality ledger,
and retries unresolved dates on every subsequent run.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .tsetmc_adapter import TsetmcAdapter

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
HISTORY_DIR = RUNTIME / "history"
QUALITY_DIR = RUNTIME / "data_quality"
RETRY_SECONDS = int(os.getenv("SMART_GAP_RETRY_SECONDS", "3600"))
MAX_ATTEMPTS = int(os.getenv("SMART_GAP_MAX_ATTEMPTS", "0"))  # 0 = unlimited


def _date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _load_history(symbol: str) -> dict[str, Any]:
    path = HISTORY_DIR / f"{symbol}.json"
    if not path.exists():
        return {"symbol": symbol, "daily_history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_history(symbol: str, payload: dict[str, Any]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    payload["daily_history"] = sorted(
        payload.get("daily_history", []), key=lambda r: int(r.get("dEven", 0)), reverse=True
    )
    payload["history_rows"] = len(payload["daily_history"])
    payload["first_history_date"] = payload["daily_history"][-1].get("dEven") if payload["daily_history"] else None
    payload["last_history_date"] = payload["daily_history"][0].get("dEven") if payload["daily_history"] else None
    payload["repaired_at"] = datetime.now(timezone.utc).isoformat()
    (HISTORY_DIR / f"{symbol}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _quality_path(symbol: str) -> Path:
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    return QUALITY_DIR / f"{symbol}.json"


def _load_quality(symbol: str) -> dict[str, Any]:
    path = _quality_path(symbol)
    if not path.exists():
        return {"symbol": symbol, "dates": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_quality(symbol: str, quality: dict[str, Any]) -> None:
    quality["checked_at"] = datetime.now(timezone.utc).isoformat()
    _quality_path(symbol).write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


def _expected_dates(start: date, end: date):
    """Iran market candidate weekdays: Saturday through Wednesday.

    Official holidays and symbol suspensions are not guessed as closed. If a
    candidate date has no source row it remains unresolved and is retried.
    """
    current = start
    while current <= end:
        if current.weekday() in (5, 6, 0, 1, 2):
            yield current
        current += timedelta(days=1)


def repair_symbol(symbol: str, *, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    history_payload = _load_history(symbol)
    rows = history_payload.get("daily_history", [])
    existing: dict[date, dict[str, Any]] = {}
    for row in rows:
        d = _date(row.get("dEven"))
        if d:
            existing[d] = row

    if not existing:
        return {"symbol": symbol, "status": "no_history", "missing": []}

    start = min(existing)
    quality = _load_quality(symbol)
    dates = quality.setdefault("dates", {})
    missing = [d for d in _expected_dates(start, today) if d not in existing]

    ins_code = str(history_payload.get("ins_code", "")).strip()
    if not ins_code:
        raise RuntimeError(f"Missing ins_code in history file for {symbol}")
    source_rows = TsetmcAdapter().daily_history(ins_code, 0)
    source_by_date = {d: row for row in source_rows if (d := _date(row.get("dEven")))}

    repaired: list[str] = []
    unresolved: list[str] = []
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
        if MAX_ATTEMPTS and entry["attempts"] >= MAX_ATTEMPTS and entry["status"] == "UNRESOLVED":
            entry["status"] = "RETRY_PENDING"

    history_payload["daily_history"] = list(existing.values())
    _save_history(symbol, history_payload)
    quality["summary"] = {
        "missing_before": len(missing),
        "repaired": len(repaired),
        "unresolved": len(unresolved),
        "next_retry_seconds": RETRY_SECONDS,
    }
    _save_quality(symbol, quality)
    return {"symbol": symbol, **quality["summary"], "repaired_dates": repaired, "unresolved_dates": unresolved}


def run(symbols: list[str]) -> None:
    while True:
        for symbol in symbols:
            try:
                result = repair_symbol(symbol)
                print(f"gap-recovery {symbol}: {result}", flush=True)
            except Exception as exc:
                print(f"gap-recovery {symbol}: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(RETRY_SECONDS)
