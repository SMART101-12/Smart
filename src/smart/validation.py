"""Multi-source market-data validation primitives."""

from __future__ import annotations

from statistics import median
from typing import Iterable

from .models import MarketDataPoint, ValidationResult


def validate_field(
    points: Iterable[MarketDataPoint],
    field: str,
    *,
    stale_after_seconds: int = 300,
    now=None,
    tolerance: float = 0.01,
) -> ValidationResult:
    """Reconcile one numeric field across sources.

    The function deliberately exposes freshness, consistency and reliability
    separately so later engines can adapt weights instead of using a single
    opaque confidence number.
    """
    rows = list(points)
    if not rows:
        raise ValueError("at least one market data point is required")

    if now is None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

    values = []
    freshness = []
    for row in rows:
        value = getattr(row, field, None)
        if value is None:
            continue
        values.append(float(value))
        age = max(0.0, (now - row.timestamp).total_seconds())
        freshness.append(max(0.0, 1.0 - age / stale_after_seconds))

    if not values:
        return ValidationResult(field, None, 0, 0.0, 0.0, 0.0, True, True)

    center = median(values)
    consistency = sum(abs(v - center) / max(abs(center), 1e-12) <= tolerance for v in values) / len(values)
    freshness_score = sum(freshness) / len(freshness)
    reliability = 0.5 * consistency + 0.5 * freshness_score

    return ValidationResult(
        field=field,
        value=center,
        source_count=len(values),
        freshness_score=freshness_score,
        consistency_score=consistency,
        reliability_score=reliability,
        is_stale=freshness_score == 0.0,
        is_conflicting=consistency < 1.0,
    )
