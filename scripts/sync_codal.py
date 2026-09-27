"""Resumable company disclosure sync and local-only per-symbol export."""
import argparse
import json
from pathlib import Path

from smart.codal import KodALSyncManager
from smart.company_financials import company_dataset, export_company
from smart.financial_history import HistoricalDataRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--force", action="store_true", help="Ignore sync TTL; reuse downloaded assets")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    repo = HistoricalDataRepository(args.database)
    result = ({"status": "LOCAL_ONLY", "data_quality": company_dataset(repo, args.symbol)["data_quality"]}
              if args.local_only else KodALSyncManager(repo).sync_company(args.symbol, args.years, args.max_pages, args.force))
    if args.export:
        result["export_path"] = export_company(repo, args.symbol, args.export)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] in {"SUCCESS", "LOCAL_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
