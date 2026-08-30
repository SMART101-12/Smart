"""Incrementally synchronize configured TSETMC symbols.

The first run for a symbol uses TSETMC's complete daily-history endpoint.  A
later run computes expected Iranian trading dates and requests only dates not
already archived.  Unresolved dates remain in ``runtime/data_quality`` for a
later retry.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.tsetmc_adapter import TsetmcAdapter


def read_symbols(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--symbols-file", default=str(ROOT / "config" / "tsetmc_symbols.txt"))
    parser.add_argument("--start-date", help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end-date", help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    symbols = args.symbols or read_symbols(Path(args.symbols_file))
    adapter = TsetmcAdapter()
    results = []
    for symbol in symbols:
        try:
            result = adapter.collect_symbol_incremental(
                symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            result = {
                "symbol": symbol,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))
    return 0 if all(item.get("status") == "COMPLETE" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
