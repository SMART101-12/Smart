"""TSETMC adapter for the Iran-side SMART agent.

Uses the community-documented cdn.tsetmc.com JSON endpoints. Network calls
run from the user's Windows/Iran connection. Collection persists both the
raw snapshot and every daily historical record for later analysis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from .snapshot_store import SnapshotStore

BASE_URL = "https://cdn.tsetmc.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.ir/",
}


class TsetmcAdapter:
    def __init__(self, store: SnapshotStore | None = None, timeout: int = 20) -> None:
        self.store = store or SnapshotStore()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, path: str) -> Any:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            if "text/html" in response.headers.get("content-type", "").lower():
                raise RuntimeError("TSETMC returned HTML instead of JSON; access may be blocked.")
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"TSETMC request failed: {url}: {exc}") from exc

    def search(self, query: str) -> list[dict[str, Any]]:
        data = self._get(f"Instrument/GetInstrumentSearch/{quote(query, safe='')}")
        return data.get("instrumentSearch", []) if isinstance(data, dict) else []

    def resolve_symbol(self, symbol: str) -> dict[str, Any]:
        rows = self.search(symbol)
        exact = [row for row in rows if row.get("lVal18AFC") == symbol or row.get("lVal30") == symbol]
        row = (exact or rows)[0] if (exact or rows) else None
        if not row or not row.get("insCode"):
            raise RuntimeError(f"Symbol not found on TSETMC: {symbol}")
        return row

    def closing_price(self, ins_code: str) -> dict[str, Any]:
        data = self._get(f"ClosingPrice/GetClosingPriceInfo/{ins_code}")
        return data.get("closingPriceInfo", data) if isinstance(data, dict) else data

    def client_type(self, ins_code: str) -> dict[str, Any]:
        data = self._get(f"ClientType/GetClientType/{ins_code}/1/0")
        return data.get("clientType", data) if isinstance(data, dict) else data

    def daily_history(self, ins_code: str, top: int = 0) -> list[dict[str, Any]]:
        data = self._get(f"ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}")
        return data.get("closingPriceDaily", []) if isinstance(data, dict) else data

    def collect_symbol(self, symbol: str) -> dict[str, Any]:
        instrument = self.resolve_symbol(symbol)
        ins_code = str(instrument["insCode"])
        observed_at = datetime.now(timezone.utc)
        history = self.daily_history(ins_code, 0)
        closing = self.closing_price(ins_code)
        clients = self.client_type(ins_code)
        payload = {
            "instrument": instrument,
            "closing_price": closing,
            "client_type": clients,
            "daily_history": history,
            "ins_code": ins_code,
            "requested_symbol": symbol,
        }
        self.store.save(symbol, "tsetmc", observed_at, payload)
        historical_rows_saved = self.store.save_daily_history(symbol, "tsetmc", observed_at, history)
        coverage = self.store.history_coverage(symbol, "tsetmc")
        return {
            "symbol": symbol,
            "ins_code": ins_code,
            "source": "tsetmc",
            "observed_at": observed_at.isoformat(),
            "history_rows": len(history),
            "historical_rows_saved": historical_rows_saved,
            "history_coverage": coverage,
            "latest_history": history[0] if history else None,
            "oldest_history": history[-1] if history else None,
            "payload": payload,
        }
