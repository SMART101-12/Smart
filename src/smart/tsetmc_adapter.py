"""TSETMC adapter for the Iran-side SMART agent.

Uses the community-documented cdn.tsetmc.com JSON endpoints. Network calls
run from the user's Windows/Iran connection. Collection persists both the
raw snapshot and every daily historical record for later analysis.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from .persian_text import normalize_persian_text
from .snapshot_store import SnapshotStore

BASE_URL = "https://cdn.tsetmc.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.ir/",
}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class TsetmcAdapter:
    def __init__(self, store: SnapshotStore | None = None, timeout: int = 20, retries: int = 3) -> None:
        self.store = store or SnapshotStore()
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, path: str) -> Any:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code in RETRYABLE_STATUS and attempt < self.retries:
                    time.sleep(1.5 * attempt)
                    continue
                response.raise_for_status()
                if "text/html" in response.headers.get("content-type", "").lower():
                    raise RuntimeError("TSETMC returned HTML instead of JSON; access may be blocked.")
                return response.json()
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1.5 * attempt)
                    continue
                break
        raise RuntimeError(f"TSETMC request failed after {self.retries} attempts: {url}: {last_error}") from last_error

    def search(self, query: str) -> list[dict[str, Any]]:
        data = self._get(f"Instrument/GetInstrumentSearch/{quote(query, safe='')}")
        return data.get("instrumentSearch", []) if isinstance(data, dict) else []

    @staticmethod
    def _is_derivative_or_non_primary(row: dict[str, Any]) -> bool:
        """Return True for instruments that should not win primary-symbol resolution."""
        ticker = str(row.get("lVal18AFC") or "")
        name = str(row.get("lVal30") or "")
        category = str(row.get("cgrValCot") or "").upper()

        # حق تقدم: TSETMC normally appends "ح" to the primary ticker.
        if ticker.endswith("ح") or name.startswith("ح .") or name.startswith("ح."):
            return True
        # Options / derivatives have flow=3 in the current TSETMC instrument search.
        if row.get("flow") == 3 or category.startswith("3"):
            return True
        # Debt / financing instruments should not be selected for stock/ETF analysis.
        if category in {"17", "16", "OT", "QD"}:
            return True
        if "اختيار" in name or "مرابحه" in name or "سلف " in name:
            return True
        return False

    @classmethod
    def _rank_search_results(cls, symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank search results deterministically, with exact primary instruments first."""
        query = normalize_persian_text(symbol)
        ranked: list[tuple[int, int, dict[str, Any]]] = []

        for index, row in enumerate(rows):
            ticker = normalize_persian_text(row.get("lVal18AFC", ""))
            name = normalize_persian_text(row.get("lVal30", ""))
            flow = row.get("flow")
            non_primary = cls._is_derivative_or_non_primary(row)

            score = 0
            if ticker == query:
                score += 1000
            if name == query:
                score += 950
            if ticker and query and ticker.replace(" ", "") == query.replace(" ", ""):
                score += 100
            if query and query in name:
                score += 40
            if query and query in ticker:
                score += 30

            # Prefer normal equity/ETF market instruments over other flows.
            if flow in {1, 2}:
                score += 50
            if row.get("sourceID") == 1:
                score += 10
            if non_primary:
                score -= 10000

            # Stable tie-breaker: preserve TSETMC result order.
            ranked.append((score, -index, row))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked]

    def resolve_symbol(self, symbol: str) -> dict[str, Any]:
        """Resolve a user symbol to one deterministic primary TSETMC instrument.

        Exact ticker/name matches always beat fuzzy matches. Persian/Arabic
        Unicode variants are normalized only for matching. Rights, options,
        debt/financing instruments and other derivatives are excluded from
        winning resolution. The selected row includes resolver metadata so
        downstream history/analysis can audit why that instrument was chosen.
        """
        query = normalize_persian_text(symbol)
        if not query:
            raise RuntimeError("Symbol must not be empty")

        rows = self.search(symbol)
        ranked = self._rank_search_results(query, rows)
        if not ranked:
            raise RuntimeError(f"Symbol not found on TSETMC: {symbol}")

        primary = ranked[0]
        if not primary.get("insCode") or self._is_derivative_or_non_primary(primary):
            raise RuntimeError(f"No primary tradable instrument found on TSETMC: {symbol}")

        resolved = dict(primary)
        normalized_ticker = normalize_persian_text(resolved.get("lVal18AFC", ""))
        normalized_name = normalize_persian_text(resolved.get("lVal30", ""))
        resolved["resolver"] = {
            "requested_symbol": symbol,
            "normalized_symbol": query,
            "match": "exact_ticker" if normalized_ticker == query else (
                "exact_name" if normalized_name == query else "ranked_search"
            ),
            "candidate_count": len(rows),
            "excluded_candidate_count": sum(self._is_derivative_or_non_primary(row) for row in rows),
        }
        return resolved

    def closing_price(self, ins_code: str) -> dict[str, Any]:
        data = self._get(f"ClosingPrice/GetClosingPriceInfo/{ins_code}")
        return data.get("closingPriceInfo", data) if isinstance(data, dict) else data

    def client_type(self, ins_code: str) -> dict[str, Any]:
        data = self._get(f"ClientType/GetClientType/{ins_code}/1/0")
        return data.get("clientType", data) if isinstance(data, dict) else data

    def closing_price_daily(self, ins_code: str, market_date: str | int) -> dict[str, Any] | None:
        """Fetch one daily closing record from TSETMC.

        The single-day endpoint is the important primitive for incremental
        synchronization.  TSETMC has returned both a dictionary and a
        one-item list for this endpoint over time, so the response is
        normalized to one row (or ``None``) here.
        """
        raw_date = str(market_date).replace("-", "").replace("/", "").strip()
        if len(raw_date) != 8 or not raw_date.isdigit():
            raise ValueError("market_date must be YYYYMMDD or YYYY-MM-DD")
        data = self._get(f"ClosingPrice/GetClosingPriceDaily/{ins_code}/{raw_date}")
        value: Any
        if isinstance(data, dict):
            value = data.get("closingPriceDaily", data)
        else:
            value = data
        if isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    row_date = str(row.get("dEven") or "").replace("-", "").replace("/", "")
                    if row_date == raw_date:
                        return row
            return next((row for row in value if isinstance(row, dict)), None)
        return value if isinstance(value, dict) else None

    def instrument_calendar(self, ins_code: str) -> list[dict[str, Any]]:
        """Return the instrument-specific trading calendar when available."""
        data = self._get(f"ClosingPrice/GetInstrumentCalendar/{ins_code}")
        rows = data.get("instrumentCalendar", data) if isinstance(data, dict) else data
        return rows if isinstance(rows, list) else []

    def daily_history(self, ins_code: str, top: int = 0) -> list[dict[str, Any]]:
        data = self._get(f"ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}")
        return data.get("closingPriceDaily", []) if isinstance(data, dict) else data

    def daily_history_incremental(
        self,
        ins_code: str,
        market_dates: list[str | int],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Fetch only the requested dates and return rows plus unresolved dates."""
        rows: list[dict[str, Any]] = []
        unresolved: list[str] = []
        for value in market_dates:
            key = str(value).replace("-", "").replace("/", "").strip()
            try:
                row = self.closing_price_daily(ins_code, key)
            except Exception:
                unresolved.append(key)
                continue
            if row is None:
                unresolved.append(key)
            else:
                rows.append(row)
        return rows, unresolved

    def collect_symbol_incremental(
        self,
        symbol: str,
        *,
        start_date: Any | None = None,
        end_date: Any | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the resumable history synchronizer for one symbol.

        Importing lazily avoids a module cycle while keeping the adapter as
        the single source-specific HTTP boundary.
        """
        from .incremental import IncrementalHistorySync

        return IncrementalHistorySync(self).sync(
            symbol,
            start_date=start_date,
            end_date=end_date,
            dry_run=dry_run,
        )

    def collect_symbol(self, symbol: str) -> dict[str, Any]:
        instrument = self.resolve_symbol(symbol)
        ins_code = str(instrument["insCode"])
        observed_at = datetime.now(timezone.utc)
        errors: list[dict[str, str]] = []

        history = self.daily_history(ins_code, 0)

        try:
            closing = self.closing_price(ins_code)
        except Exception as exc:
            closing = None
            errors.append({"component": "closing_price", "error": str(exc)})

        try:
            clients = self.client_type(ins_code)
        except Exception as exc:
            clients = None
            errors.append({"component": "client_type", "error": str(exc)})

        payload = {
            "instrument": instrument,
            "closing_price": closing,
            "client_type": clients,
            "daily_history": history,
            "ins_code": ins_code,
            "requested_symbol": symbol,
            "collection_errors": errors,
            "data_quality": "partial" if errors else "complete",
        }
        self.store.save(symbol, "tsetmc", observed_at, payload)
        history_persistence = self.store.save_daily_history_incremental(symbol, "tsetmc", observed_at, history)
        coverage = self.store.history_coverage(symbol, "tsetmc")
        return {
            "symbol": symbol,
            "ins_code": ins_code,
            "source": "tsetmc",
            "observed_at": observed_at.isoformat(),
            "history_rows": len(history),
            "history_persistence": history_persistence,
            "history_coverage": coverage,
            "latest_history": history[0] if history else None,
            "oldest_history": history[-1] if history else None,
            "collection_errors": errors,
            "data_quality": "partial" if errors else "complete",
            "payload": payload,
        }
