from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from smart_v2.core.models import ValidationIssue


def parse_tsetmc_date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def validate_rows(rows: Iterable[dict[str, Any]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: set[date] = set()
    for row in rows:
        d = parse_tsetmc_date(row.get("dEven"))
        if d is None:
            issues.append(ValidationIssue("INVALID_DATE", "ERROR", "Invalid dEven", field="dEven"))
            continue
        if d in seen:
            issues.append(ValidationIssue("DUPLICATE_DATE", "ERROR", "Duplicate trading date", d.isoformat()))
        seen.add(d)

        numeric_fields = ("pOpen", "pHigh", "pLow", "pClosing", "pDrCotVal", "zTotTran", "qTotTran5J", "qTotCap")
        for field in numeric_fields:
            if field in row and row[field] not in (None, ""):
                try:
                    value = float(row[field])
                except (TypeError, ValueError):
                    issues.append(ValidationIssue("INVALID_NUMBER", "ERROR", f"Non-numeric {field}", d.isoformat(), field))
                    continue
                if value < 0:
                    issues.append(ValidationIssue("NEGATIVE_VALUE", "ERROR", f"Negative {field}", d.isoformat(), field))

        try:
            low = float(row.get("pLow"))
            high = float(row.get("pHigh"))
            if low > high:
                issues.append(ValidationIssue("OHLC_RANGE", "ERROR", "Low is greater than high", d.isoformat()))
        except (TypeError, ValueError):
            pass
    return issues
