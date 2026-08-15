"""Core data models used by the SMART pipeline."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class MarketDataPoint:
    """A normalized market observation from one source."""

    symbol: str
    timestamp: datetime
    source: str
    price: Optional[float] = None
    volume: Optional[float] = None
    trade_value: Optional[float] = None
    trade_count: Optional[int] = None
    quality_score: Optional[float] = None


@dataclass(frozen=True)
class ValidationResult:
    """Reconciled value and validation metadata for one field."""

    field: str
    value: Optional[float]
    source_count: int
    freshness_score: float
    consistency_score: float
    reliability_score: float
    is_stale: bool = False
    is_conflicting: bool = False


@dataclass(frozen=True)
class VolumeQualityResult:
    """Volume and turnover quality assessment."""

    volume_ratio: Optional[float]
    value_ratio: Optional[float]
    abnormal_volume: bool
    quality_score: float
    reason: str
