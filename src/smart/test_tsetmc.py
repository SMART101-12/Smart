"""Command-line smoke test for the local TSETMC connection."""

from __future__ import annotations

import argparse
import json

from .tsetmc_adapter import TsetmcAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="عیار")
    args = parser.parse_args()
    result = TsetmcAdapter().collect_symbol(args.symbol)
    print(json.dumps({
        "symbol": result["symbol"],
        "ins_code": result["ins_code"],
        "source": result["source"],
        "observed_at": result["observed_at"],
        "history_rows": result["history_rows"],
        "latest_history": result["latest_history"],
        "saved": True,
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
