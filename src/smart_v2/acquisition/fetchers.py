from __future__ import annotations

import os
from typing import Any, Dict, List
from urllib.parse import quote

import requests

from .errors import DataFetchError


class BaseFetcher:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 SMART-acquisition/2.1",
                "Accept": "application/json, text/plain, */*",
            }
        )


class TSETMCFetcher(BaseFetcher):
    """TSETMC HTTP boundary used by the V2 acquisition service."""

    base_url = "https://cdn.tsetmc.com/api"

    def __init__(self, timeout: int = 10, *, allow_fallback: bool | None = None):
        super().__init__(timeout)
        self.allow_fallback = (
            os.getenv("SMART_ALLOW_SYNTHETIC_TSETMC", "1") == "1"
            if allow_fallback is None
            else allow_fallback
        )

    def _get(self, path: str) -> Any:
        try:
            response = self.session.get(
                f"{self.base_url}/{path.lstrip('/')}", timeout=self.timeout
            )
            response.raise_for_status()
            if "text/html" in response.headers.get("content-type", "").lower():
                raise DataFetchError("TSETMC returned HTML instead of JSON")
            return response.json()
        except DataFetchError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise DataFetchError(f"TSETMC request failed: {path}") from exc

    def fetch_market_watch(self) -> List[Dict[str, Any]]:
        try:
            data = self._get(
                "ClosingPrice/GetMarketWatch?market=0&paperTypes[0]=1&"
                "paperTypes[1]=2&paperTypes[2]=3&withBestLimits=false&hEven=0&RefID=0"
            )
            rows = (
                (data.get("marketwatch") or data.get("marketWatch") or [])
                if isinstance(data, dict)
                else []
            )
            if isinstance(rows, list) and rows:
                # Some TSETMC responses contain the universe while all quote
                # fields are zero during a closed/blocked session.  Do not
                # pass that unusable payload downstream as a valid snapshot.
                usable = any(
                    _positive_number(row.get(key))
                    for row in rows
                    if isinstance(row, dict)
                    for key in (
                        "pClosing",
                        "pcl",
                        "pDrCotVal",
                        "pdv",
                        "qTotTran5J",
                        "qtj",
                    )
                )
                if usable:
                    return rows
        except DataFetchError:
            if not self.allow_fallback:
                raise
        if self.allow_fallback:
            return [
                {
                    "insCode": "fixture-1",
                    "lva": "SMART_FIXTURE",
                    "pClosing": 100.0,
                    "pDrCotVal": 100.0,
                    "pMax": 101.0,
                    "pMin": 99.0,
                    "pFirst": 100.0,
                    "qTotTran5J": 1000.0,
                    "qTotCap": 100000.0,
                    "zTotTran": 10.0,
                    "source": "offline_fixture",
                    "data_quality": "synthetic_fixture",
                }
            ]
        return []

    def search_symbol(self, symbol: str) -> dict[str, Any]:
        data = self._get(f"Instrument/GetInstrumentSearch/{quote(symbol, safe='')}")
        rows = data.get("instrumentSearch", []) if isinstance(data, dict) else []
        if not rows:
            raise DataFetchError(f"TSETMC symbol not found: {symbol}")
        exact = [
            row for row in rows if str(row.get("lVal18AFC") or "").strip() == symbol
        ]
        result = (exact or rows)[0]
        if not result.get("insCode"):
            raise DataFetchError(f"TSETMC symbol has no InsCode: {symbol}")
        return result


class MacroFetcher(BaseFetcher):
    """Macro boundary with an explicitly labeled offline fixture."""

    def __init__(self, timeout: int = 10, *, allow_fallback: bool | None = None):
        super().__init__(timeout)
        self.allow_fallback = (
            os.getenv("SMART_ALLOW_SYNTHETIC_MACRO", "1") == "1"
            if allow_fallback is None
            else allow_fallback
        )

    def fetch_macro_snapshot(self) -> Dict[str, Any]:
        if not self.allow_fallback:
            return {
                "usd_irr": 0.0,
                "usd_tether": 0.0,
                "xau_usd": 0.0,
                "cbi_rate": 0.0,
                "source": "unavailable",
                "data_quality": "unavailable",
            }
        return {
            "usd_irr": 600000.0,
            "usd_tether": 605000.0,
            "xau_usd": 2400.0,
            "cbi_rate": 0.23,
            "source": "fallback_fixture",
            "data_quality": "synthetic_fixture",
        }


__all__ = ["BaseFetcher", "TSETMCFetcher", "MacroFetcher"]


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
