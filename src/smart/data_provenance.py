"""Data provenance and coverage reporting for every SMART analysis.

The engine distinguishes the observation date from the retrieval date and
reports the historical coverage actually available to the analyzer. It never
claims a multi-year validation window unless the stored snapshots prove it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class DataCoverage:
    symbol: str
    source: str
    latest_observation_date: date | None
    retrieved_at: datetime
    earliest_observation_date: date | None
    coverage_days: int
    coverage_years: float
    current_day_confirmed: bool
    status: str

    def report(self) -> dict:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "latest_observation_date": self.latest_observation_date.isoformat() if self.latest_observation_date else None,
            "retrieved_at": self.retrieved_at.isoformat(),
            "earliest_observation_date": self.earliest_observation_date.isoformat() if self.earliest_observation_date else None,
            "coverage_days": self.coverage_days,
            "coverage_years": round(self.coverage_years, 2),
            "current_day_confirmed": self.current_day_confirmed,
            "status": self.status,
        }


def build_coverage(
    symbol: str,
    source: str,
    observation_dates: Iterable[date],
    *,
    market_today: date | None = None,
    retrieved_at: datetime | None = None,
) -> DataCoverage:
    dates = sorted(set(observation_dates))
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    market_today = market_today or retrieved_at.date()

    if not dates:
        return DataCoverage(symbol, source, None, retrieved_at, None, 0, 0.0, False, "no_verified_history")

    earliest, latest = dates[0], dates[-1]
    days = (latest - earliest).days + 1
    current = latest == market_today
    status = "current_and_historical" if current else "historical_only"
    return DataCoverage(symbol, source, latest, retrieved_at, earliest, days, days / 365.25, current, status)
