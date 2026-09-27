from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_verified_day(root: Path, symbol: str, ins_code: str, row: dict[str, Any]) -> Path:
    """Write one verified daily record using YYYY/MM/DD partitioning.

    This function intentionally refuses to write unless the caller has already
    completed validation. Validation is an upstream responsibility.
    """
    raw_date = str(row.get("dEven") or "")
    if len(raw_date) != 8 or not raw_date.isdigit():
        raise ValueError("Verified record requires dEven in YYYYMMDD form")
    year, month, _ = raw_date[:4], raw_date[4:6], raw_date[6:]
    target_dir = root / f"{symbol}_{ins_code}" / year / month
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{raw_date}.json"
    target.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
