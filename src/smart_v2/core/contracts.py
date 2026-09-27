"""Stable contracts between SMART V2 modules.

The contracts intentionally contain no TSETMC, processing, or AI implementation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    field: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    run_id: str
    status: str
    records_tested: int
    passed: int
    failed: int
    issues: tuple[ValidationIssue, ...] = ()
    report_path: str | None = None


@dataclass(frozen=True)
class DataArtifact:
    symbol_en: str
    ins_code: str
    path: str
    created_at: datetime
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
