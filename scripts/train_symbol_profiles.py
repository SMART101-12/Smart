"""Train and persist separate adaptive entry profiles from live TSETMC history."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.symbol_learning import FOCUS_SYMBOLS, summarize_profile
from smart.tsetmc import focus_symbol_profiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train independent long-only adaptive entry profiles from TSETMC history."
    )
    parser.add_argument(
        "--symbols",
        default=",".join(FOCUS_SYMBOLS),
        help="Comma-separated TSETMC tickers (default: فولاد,پالایش,فملی,فجر)",
    )
    parser.add_argument("--years", type=int, default=10, help="Maximum calendar years to study")
    parser.add_argument("--initial-history", type=int, default=20)
    parser.add_argument("--evaluation-window", type=int, default=30)
    parser.add_argument("--transaction-cost-pct", type=float, default=0.35)
    args = parser.parse_args()

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    result = asyncio.run(
        focus_symbol_profiles(
            symbols,
            years=args.years,
            initial_history=args.initial_history,
            evaluation_window=args.evaluation_window,
            transaction_cost_pct=args.transaction_cost_pct,
        )
    )
    output = dict(result)
    output["results"] = [summarize_profile(item) for item in result.get("results", [])]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result.get("results") else 2


if __name__ == "__main__":
    raise SystemExit(main())
