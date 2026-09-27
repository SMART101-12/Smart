#!/usr/bin/env python3
"""Split AYAR raw TSETMC history into monthly JSON files.

Source:
  runtime/market_raw/history/عیار/raw/2026-08-18.json

Output:
  runtime/market_raw/history/عیار/monthly/YYYY-MM.json

The script preserves the raw closingPriceDaily records and adds a small
metadata envelope. It is intentionally deterministic and does not alter
price/volume fields.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/market_raw/history/عیار/raw/2026-08-18.json"
OUT = ROOT / "runtime/market_raw/history/عیار/monthly"


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    content = payload.get("content", payload)
    if isinstance(content, str):
        content = json.loads(content)

    records = content.get("closingPriceDaily", [])
    if not isinstance(records, list):
        raise TypeError("closingPriceDaily must be a list")

    months: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        date = str(record.get("dEven", ""))
        if len(date) != 8 or not date.isdigit():
            continue
        month = f"{date[:4]}-{date[4:6]}"
        months[month].append(record)

    OUT.mkdir(parents=True, exist_ok=True)
    for month, rows in sorted(months.items()):
        rows.sort(key=lambda r: int(r["dEven"]))
        result = {
            "symbol": "عیار",
            "source": "tsetmc",
            "source_file": str(SOURCE.relative_to(ROOT)),
            "month": month,
            "record_count": len(rows),
            "records": rows,
        }
        target = OUT / f"{month}.json"
        target.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"{target}: {len(rows)} records")


if __name__ == "__main__":
    main()
