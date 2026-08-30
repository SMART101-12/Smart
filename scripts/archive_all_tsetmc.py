"""Build canonical archives for the existing all-market TSETMC raw history.

The script is intentionally separate from downloading.  It can be rerun after
an interrupted job, keeps the raw source tree untouched, and writes one
aggregate quality report.  Use ``--limit`` for a smoke run before processing
the complete universe.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.archive import archive_monthly, safe_symbol


RAW_ROOT = ROOT / "runtime" / "market_raw" / "history"
CANONICAL_ROOT = ROOT / "runtime" / "market_processed" / "canonical"
REPORT_ROOT = ROOT / "runtime" / "data_quality"

# Windows PowerShell commonly starts Python with a cp1252 stdout stream.
# Reconfigure when possible so Persian symbols do not abort a long archive job.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def load_symbol_rows(directory: Path) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    metadata: dict = {"symbol": directory.name}
    for path in sorted(directory.glob("*.json")):
        if path.parent.name == "raw":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for key in ("symbol", "ins_code", "source", "source_url"):
            if payload.get(key) not in (None, ""):
                metadata[key] = payload[key]
        source_rows = payload.get("records") or payload.get("daily_history") or []
        if isinstance(source_rows, list):
            rows.extend(item for item in source_rows if isinstance(item, dict))
    return rows, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--report", default=str(REPORT_ROOT / "all_market_canonical.json"))
    parser.add_argument(
        "--output-root",
        default=str(CANONICAL_ROOT),
        help="Derived canonical archive root (raw input is never modified).",
    )
    parser.add_argument(
        "--strict-ohlc",
        action="store_true",
        help="Treat adjusted-close vs raw high/low mismatches as errors.",
    )
    args = parser.parse_args()

    directories = sorted(path for path in RAW_ROOT.iterdir() if path.is_dir())
    if args.symbols:
        requested = {safe_symbol(value) for value in args.symbols}
        directories = [path for path in directories if path.name in requested]
    if args.limit > 0:
        directories = directories[: args.limit]

    results: list[dict] = []
    for index, directory in enumerate(directories, 1):
        print(f"[{index}/{len(directories)}] {directory.name}", flush=True)
        rows, metadata = load_symbol_rows(directory)
        if not rows:
            results.append(
                {"symbol": directory.name, "status": "NO_ROWS", "input_files": 0}
            )
            continue
        try:
            report = archive_monthly(
                directory.name,
                rows,
                root=args.output_root,
                ins_code=str(metadata.get("ins_code") or ""),
                source=str(metadata.get("source") or "TSETMC"),
                strict_ohlc=args.strict_ohlc,
                metadata={
                    **metadata,
                    "input_layer": "runtime/market_raw/history",
                },
            )
            results.append(
                {
                    "symbol": directory.name,
                    "status": "PASS"
                    if report["quality"]["status"] in {"PASS", "PASS_WITH_WARNINGS"}
                    else "FAIL",
                    "quality_status": report["quality"]["status"],
                    "input_rows": report["deduplication"]["input_rows"],
                    "canonical_rows": report["quality"]["rows"],
                    "duplicate_dates": report["deduplication"]["duplicate_dates"],
                    "quality_issues": report["quality"]["issue_count"],
                    "archive_paths": report["archive_paths"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "symbol": directory.name,
                    "status": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    aggregate = {
        "schema_version": "1.0",
        "source": "TSETMC",
        "input_root": str(RAW_ROOT),
        "output_root": str(Path(args.output_root)),
        "started/finished_at": datetime.now(timezone.utc).isoformat(),
        "symbol_count": len(directories),
        "pass_count": sum(item["status"] == "PASS" for item in results),
        "fail_count": sum(item["status"] == "FAIL" for item in results),
        "error_count": sum(item["status"] == "ERROR" for item in results),
        "no_rows_count": sum(item["status"] == "NO_ROWS" for item in results),
        "results": results,
    }
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in aggregate.items() if key != "results"}, ensure_ascii=False, indent=2))
    return 0 if aggregate["error_count"] == 0 and aggregate["fail_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
