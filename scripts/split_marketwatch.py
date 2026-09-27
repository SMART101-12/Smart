"""Split one raw TSETMC MarketWatch snapshot into symbol-level raw records."""
from __future__ import annotations

import argparse
from pathlib import Path

from smart_v2.acquisition.marketwatch_splitter import MarketWatchSplitter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--date", required=True, dest="source_date")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/raw_market/symbols"),
    )
    args = parser.parse_args()

    written = MarketWatchSplitter().split(args.source, args.output_root, args.source_date)
    print(f"SOURCE={args.source}")
    print(f"WRITTEN={len(written)}")
    print(f"OUTPUT_ROOT={args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
