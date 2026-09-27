"""Incrementally update SMART's global-market archive from FRED."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.global_market import DEFAULT_SERIES, GlobalMarketArchive


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value.replace("/", "-"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", action="append", choices=sorted(DEFAULT_SERIES))
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date")
    parser.add_argument("--retry-unavailable", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    start = parse_date(args.start_date)
    end = parse_date(args.end_date) or (
        datetime.now(timezone.utc).date() - timedelta(days=1)
    )
    report = GlobalMarketArchive().sync_many(
        args.series,
        start_date=start,
        end_date=end,
        dry_run=args.dry_run,
        retry_unavailable=args.retry_unavailable,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
