from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    date: str | None = None
    field: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    symbol: str
    ins_code: str
    status: str = "PASS"
    checked_records: int = 0
    passed_records: int = 0
    failed_records: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_issue(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        self.status = "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ins_code": self.ins_code,
            "status": self.status,
            "checked_records": self.checked_records,
            "passed_records": self.passed_records,
            "failed_records": self.failed_records,
            "issues": [issue.__dict__ for issue in self.issues],
            "checks": self.checks,
        }
