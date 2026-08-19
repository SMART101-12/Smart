from __future__ import annotations

from typing import Any

from smart_v2.core.models import ValidationResult
from smart_v2.validation.validators import validate_rows


def validate_symbol_payload(payload: dict[str, Any]) -> ValidationResult:
    instrument = payload.get("instrument") or {}
    symbol = str(payload.get("requested_symbol") or instrument.get("lVal18AFC") or "")
    ins_code = str(payload.get("ins_code") or instrument.get("insCode") or "")
    rows = payload.get("daily_history") or []
    result = ValidationResult(symbol=symbol, ins_code=ins_code, checked_records=len(rows))
    issues = validate_rows(row for row in rows if isinstance(row, dict))
    result.issues.extend(issues)
    result.failed_records = len({issue.date for issue in issues if issue.date})
    result.passed_records = max(0, result.checked_records - result.failed_records)
    result.status = "FAIL" if issues else "PASS"
    result.checks["record_validation"] = {
        "status": "FAIL" if issues else "PASS",
        "issue_count": len(issues),
    }
    return result
