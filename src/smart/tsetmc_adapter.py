"""TSETMC adapter using the community-documented cdn.tsetmc.com JSON API.

The API is reported to favor Iranian IPs. This adapter therefore belongs in
the Iran Data Agent and is not assumed to work from foreign hosting.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from .snapshot_store import SnapshotStore

BASE_URL = "https://cdn.tsetmc.com/api"


class TsetmcAdapter:
    def __init__(self, store: SnapshotStore | None = None, timeout: int = 15) -> None:
        self.store = store or SnapshotStore()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SMART-IranDataAgent/0.1",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.tsetmc.ir/",
        })

    def _get(self, path: str) -> Any:
        response = self.session.get(f"{BASE_URL}/{path.lstrip('/')}", timeout=self.timeout)
        response.raise_for_status()
        if "json" not in response.headers.get("content-type", "").lower():
            raise RuntimeError("TSETMC returned a non-JSON response; possible block or endpoint change")
        return response.json()

    def search(self, query: str) -> list[dict[str, Any]]:
        data = self._get(f"Instrument/InstrumentSearch/{query}")
        return data.get("instrumentSearch", data) if isinstance(data, dict) else data

    def closing_price(self, ins_code: str) -> dict[str, Any]:
        data = self._get(f"ClosingPrice/GetClosingPriceInfo/{ins_code}")
        return data.get("closingPriceInfo", data) if isinstance(data, dict) else data

    def client_type(self, ins_code: str) -> dict[str, Any]:
        data = self._get(f"ClientType/GetClientType/{ins_code}/1/0")
        return data.get("clientType", data) if isinstance(data, dict) else data

    def daily_history(self, ins_code: str, top: int = 0) -> list[dict[str, Any]]:
        data = self._get(f"ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}")
        return data.get("closingPriceDaily", data) if isinstance(data, dict) else data

    def collect(self, symbol: str, ins_code: str) -> dict[str, Any]:
        observed_at = datetime.now(timezone.utc)
        payload = {
            "closing_price": self.closing_price(ins_code),
            "client_type": self.client_type(ins_code),
            "daily_history": self.daily_history(ins_code),
            "ins_code": ins_code,
            "requested_symbol": symbol,
        }
        self.store.save(symbol, "tsetmc", observed_at, payload)
        return {
            "symbol": symbol,
            "source": "tsetmc",
            "observed_at": observed_at.isoformat(),
            "payload": payload,
        }
