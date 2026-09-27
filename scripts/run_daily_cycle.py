"""Run a checkpointed SMART watchlist cycle from a terminal or scheduler."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.daily_cycle import (  # noqa: E402
    ActiveRunError,
    DailyRunStore,
    execute_daily_run,
    normalize_symbols,
)
from smart.tsetmc import FOCUS_SYMBOLS, live_initial_analysis  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one SMART daily watchlist cycle")
    parser.add_argument("symbols", nargs="*", default=list(FOCUS_SYMBOLS))
    parser.add_argument("--max-age-days", type=int, default=3)
    parser.add_argument("--symbol-timeout", type=float, default=120.0)
    args = parser.parse_args()
    try:
        symbols = normalize_symbols(args.symbols)
        store = DailyRunStore()
        report = store.create(symbols, max_age_days=args.max_age_days)
    except ActiveRunError as exc:
        print(json.dumps({"status": "busy", "run_id": exc.run_id}, ensure_ascii=False))
        return 3
    except ValueError as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    final = asyncio.run(execute_daily_run(store, report["run_id"], live_initial_analysis,
                                          symbol_timeout=args.symbol_timeout))
    print(json.dumps(final, ensure_ascii=False, indent=2))
    return 0 if final["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
