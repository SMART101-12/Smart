from __future__ import annotations

from typing import Any

from smart.tsetmc_adapter import TsetmcAdapter


class AcquisitionService:
    """V2 boundary around the existing TSETMC acquisition implementation.

    The existing adapter remains the source of truth for network collection;
    this service only exposes it to V2 and does not process market data.
    """

    def __init__(self, adapter: TsetmcAdapter | None = None) -> None:
        self.adapter = adapter or TsetmcAdapter()

    def collect(self, symbol: str) -> dict[str, Any]:
        return self.adapter.collect_symbol(symbol)
