"""Source collection boundary for SMART.

Collectors return normalized observations and always persist the raw snapshot
before analysis. Network-specific adapters can be plugged in without changing
the storage or analysis layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .snapshot_store import SnapshotStore


class Collector:
    def __init__(self, store: SnapshotStore | None = None) -> None:
        self.store = store or SnapshotStore()

    def collect(self, symbol: str, source: str, fetcher: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
        observed_at = datetime.now(timezone.utc)
        payload = fetcher(symbol)
        if not isinstance(payload, dict):
            raise TypeError("source adapter must return a dictionary")
        payload = {**payload, "requested_symbol": symbol}
        self.store.save(symbol, source, observed_at, payload)
        return {
            "symbol": symbol,
            "source": source,
            "observed_at": observed_at.isoformat(),
            "market_date": observed_at.date().isoformat(),
            "payload": payload,
            "fresh_for_today": self.store.is_fresh_for_today(symbol, source, observed_at.date()),
        }
