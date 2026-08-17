"""Incremental historical Data Entry for Iran Basic Metals equities.

Usage from repository root:
    $env:PYTHONPATH = ".\src"
    .\.venv\Scripts\python.exe scripts\data_entry_basic_metals.py --top 1000

The job:
- uses the existing SMART TSETMC adapter;
- keeps the symbol universe in one auditable list;
- verifies the instrument's industry metadata when available;
- stores daily history in the existing SQLite SnapshotStore;
- writes a Git-tracked JSON history file for each symbol;
- upserts by market date, so reruns do not duplicate rows;
- writes a JSON run report under data/data_entry/basic_metals/.

No price values are hard-coded. TSETMC is the source used by this ingestion job.
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


def _flatten_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if "industry" in str(key).lower() or "group" in str(key).lower() or "صنعت" in str(key):
                if isinstance(item, (str, int, float)):
                    out.append(str(item))
            out.extend(_flatten_strings(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_flatten_strings(item))
    return out


def _industry_matches(info: dict[str, Any]) -> bool | None:
    values = _flatten_strings(info)
    if not values:
        return None
    normalized = " ".join(values).replace("ي", "ی").replace("ك", "ک")
    return INDUSTRY_NAME in normalized or "basic metals" in normalized.lower()


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


async def ingest_symbol(symbol: str, store: SnapshotStore, top: int) -> dict[str, Any]:
    try:
        found = await search_symbol(symbol)
        ins_code = str(found.get("insCode") or "")
        if not ins_code:
            raise TSETMCError("instrument code missing")

        info = await instrument_info(ins_code)
        industry_match = _industry_matches(info)
        if industry_match is False:
            return {"symbol": symbol, "status": "industry_mismatch", "ins_code": ins_code}

        rows = await daily_history(ins_code, top=top)
        now = datetime.now(timezone.utc)
        result = store.save_daily_history_incremental(
            symbol=symbol,
            source=SOURCE,
            observed_at=now,
            rows=rows,
            date_key="dEven",
        )
        _write_git_history(symbol, rows, ins_code, industry_match)
        return {
            "symbol": symbol,
            "status": "ok",
            "ins_code": ins_code,
            "industry_match": industry_match,
            "fetched_rows": len(rows),
            **result,
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
