"""Incremental historical Data Entry for Iran Basic Metals equities.

Run from repository root:
    $env:PYTHONPATH = ".\src"
    .\.venv\Scripts\python.exe scripts\data_entry_basic_metals.py --top 1000

The job uses the existing SMART TSETMC adapter and SnapshotStore. It retries
TSETMC history requests, keeps per-symbol Git JSON history, and never writes
hard-coded market prices.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.snapshot_store import SnapshotStore
from smart.tsetmc import TSETMCError, daily_history, instrument_info, search_symbol

SOURCE = "TSETMC"
INDUSTRY_NAME = "فلزات اساسی"

BASIC_METALS_SYMBOLS = [
    "فملی", "فولاد", "فخوز", "ذوب", "فایرا", "فاسمین", "فزرین",
    "فرآور", "فروس", "فزر", "فجهان", "فسبزوار", "فصبا", "فخاس",
    "فجر", "فولاژ", "فپنتا", "فسپا", "فگستر", "فافق", "فسوژ",
    "فمراد", "فلوله", "فرود", "فنوال", "فباهنر", "فاما", "کاوه",
    "ارفع", "هرمز", "میدکو", "کویر", "فغدیر", "فنورد", "فسازان",
    "فوکا", "کمنگنز", "کرومیت", "کدما",
]

RETRY_DELAYS = (2, 5, 10)
RETRY_TOPS = (1000, 500, 200)


def _normalize(value: Any) -> str:
    return str(value).strip().replace("ي", "ی").replace("ك", "ک")


def _collect_industry_values(value: Any, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = _normalize(key).lower()
            if any(token in key_text for token in ("industry", "group", "industryname", "گروه", "صنعت")):
                if isinstance(item, (str, int, float)):
                    out.append(_normalize(item))
            _collect_industry_values(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_industry_values(item, out)


def _industry_matches(info: dict[str, Any]) -> bool | None:
    values: list[str] = []
    _collect_industry_values(info, values)
    if not values:
        return None
    joined = " | ".join(values).lower()
    return "فلزات اساسی" in joined or "basic metals" in joined


def _merge_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge by market date while preserving the newest payload."""
    merged: dict[str, dict[str, Any]] = {}
    for row in existing + incoming:
        raw = row.get("dEven") or row.get("date") or row.get("market_date")
        if raw is None:
            continue
        key = str(raw).strip().replace("/", "-")
        merged[key] = row
    return [merged[key] for key in sorted(merged)]


def _read_git_history(symbol: str) -> list[dict[str, Any]]:
    path = ROOT / "data" / "data_entry" / "basic_metals" / "history" / f"{symbol}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows", [])
        return rows if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_git_history(symbol: str, rows: list[dict[str, Any]], ins_code: str, industry_match: bool | None) -> None:
    out_dir = ROOT / "data" / "data_entry" / "basic_metals" / "history"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "ins_code": ins_code,
        "industry": INDUSTRY_NAME,
        "industry_match": industry_match,
        "source": SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }
    (out_dir / f"{symbol}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _fetch_history_with_retry(ins_code: str, top: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    for index, requested_top in enumerate(RETRY_TOPS):
        try:
            rows = await daily_history(ins_code, top=min(top, requested_top))
            return rows, errors
        except Exception as exc:
            errors.append(f"top={min(top, requested_top)}: {exc}")
            if index < len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[index])
    raise TSETMCError("; ".join(errors))


async def ingest_symbol(symbol: str, store: SnapshotStore, top: int) -> dict[str, Any]:
    try:
        found = await search_symbol(symbol)
        ins_code = str(found.get("insCode") or "")
        if not ins_code:
            raise TSETMCError("instrument code missing")

        info = await instrument_info(ins_code)
        industry_match = _industry_matches(info)
        if industry_match is False:
            return {
                "symbol": symbol,
                "status": "industry_mismatch",
                "ins_code": ins_code,
                "industry_match": False,
            }

        rows, retry_errors = await _fetch_history_with_retry(ins_code, top)
        now = datetime.now(timezone.utc)
        db_result = store.save_daily_history_incremental(
            symbol=symbol,
            source=SOURCE,
            observed_at=now,
            rows=rows,
            date_key="dEven",
        )

        existing = _read_git_history(symbol)
        merged = _merge_rows(existing, rows)
        _write_git_history(symbol, merged, ins_code, industry_match)

        return {
            "symbol": symbol,
            "status": "ok",
            "ins_code": ins_code,
            "industry_match": industry_match,
            "fetched_rows": len(rows),
            "git_rows": len(merged),
            "retry_count": len(retry_errors),
            "retry_errors": retry_errors,
            **db_result,
            "coverage": store.history_coverage(symbol, SOURCE),
        }
    except Exception as exc:
        return {"symbol": symbol, "status": "error", "error": str(exc)}


async def main(top: int) -> int:
    store = SnapshotStore()
    results: list[dict[str, Any]] = []

    for symbol in BASIC_METALS_SYMBOLS:
        print(f"[SMART][basic-metals] {symbol}")
        result = await ingest_symbol(symbol, store, top)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    report_dir = ROOT / "data" / "data_entry" / "basic_metals"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "industry": INDUSTRY_NAME,
        "source": SOURCE,
        "top": top,
        "symbols_requested": BASIC_METALS_SYMBOLS,
        "results": results,
    }
    report_path = report_dir / "latest_run.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(r["status"] == "ok" for r in results)
    mismatches = sum(r["status"] == "industry_mismatch" for r in results)
    errors = sum(r["status"] == "error" for r in results)
    print(f"DONE: ok={ok}, industry_mismatch={mismatches}, errors={errors}")
    print(f"REPORT: {report_path}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SMART Basic Metals historical Data Entry")
    parser.add_argument("--top", type=int, default=1000, help="number of TSETMC daily rows requested per symbol")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.top)))
