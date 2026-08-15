"""Command-line smoke test for the local TSETMC connection."""

from __future__ import annotations

import argparse
import json
from datetime import date

from .tsetmc_adapter import TsetmcAdapter


def _date_value(row: dict) -> str | None:
    value = row.get("dEven") or row.get("date") or row.get("tradeDate")
    if value is None:
        return None
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="عیار")
    args = parser.parse_args()
    result = TsetmcAdapter().collect_symbol(args.symbol)
    history = result.get("payload", {}).get("daily_history", [])
    dates = [_date_value(row) for row in history]
    dates = [d for d in dates if d]

    first_date = min(dates) if dates else None
    last_date = max(dates) if dates else None
    coverage_days = None
    if first_date and last_date and len(first_date) == 8 and len(last_date) == 8:
        try:
            first = date(int(first_date[:4]), int(first_date[4:6]), int(first_date[6:]))
            last = date(int(last_date[:4]), int(last_date[4:6]), int(last_date[6:]))
            coverage_days = (last - first).days + 1
        except ValueError:
            pass

    print(json.dumps({
        "symbol": result["symbol"],
        "ins_code": result["ins_code"],
        "source": result["source"],
        "observed_at": result["observed_at"],
        "history_rows": result["history_rows"],
        "first_history_date": first_date,
        "last_history_date": last_date,
        "coverage_days": coverage_days,
        "latest_history": result["latest_history"],
        "saved": True,
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
