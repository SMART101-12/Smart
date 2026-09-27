"""Global-market data adapters and incremental archive.

The default provider is the Federal Reserve Bank of St. Louis FRED graph CSV
endpoint.  It is a stable, public, read-only endpoint and does not require an
API key for the small daily series used by SMART.  Provider failures are
reported explicitly; no placeholder prices are generated.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DEFAULT_SERIES = {
    # Daily macro and market proxies available from FRED.  The gold series is
    # an explicitly named Nasdaq gold index (not spot XAU/USD), so consumers
    # cannot accidentally treat it as a currency quote.
    "us10y": "DGS10",
    "us10y_real": "DFII10",
    "trade_weighted_usd": "DTWEXBGS",
    "eur_usd": "DEXUSEU",
    "sp500": "SP500",
    "nasdaq": "NASDAQCOM",
    "vix": "VIXCLS",
    "wti": "DCOILWTICO",
    "gold_index": "NASDAQQGLDI",
    "gold_volatility": "GVZCLS",
}

SERIES_DESCRIPTIONS = {
    "us10y": "US 10-year Treasury constant maturity yield",
    "us10y_real": "US 10-year inflation-indexed Treasury yield",
    "trade_weighted_usd": "Broad trade-weighted US dollar index",
    "eur_usd": "USD per euro reference rate",
    "sp500": "S&P 500 close",
    "nasdaq": "NASDAQ Composite close",
    "vix": "CBOE volatility index",
    "wti": "West Texas Intermediate spot price",
    "gold_index": "NASDAQ gold commodity index proxy",
    "gold_volatility": "CBOE gold volatility index",
}


@dataclass(frozen=True)
class GlobalObservation:
    series: str
    source_id: str
    observation_date: str
    value: float
    retrieved_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "series": self.series,
            "source_id": self.source_id,
            "observation_date": self.observation_date,
            "value": self.value,
            "retrieved_at": self.retrieved_at,
        }


class FREDClient:
    """Small dependency-injected FRED client suitable for tests and cron."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: int = 30,
        base_url: str = FRED_CSV_URL,
        series_map: dict[str, str] | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.base_url = base_url
        self.series_map = {**DEFAULT_SERIES, **(series_map or {})}
        self.session.headers.update({"User-Agent": "SMART-global-data/1.0"})

    def fetch_series(
        self,
        series: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[GlobalObservation]:
        source_id = self.series_map.get(series, series)
        params = {"id": source_id}
        if start_date:
            params["cosd"] = start_date.isoformat()
        if end_date:
            params["coed"] = end_date.isoformat()
        response = self.session.get(self.base_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        raw_content = getattr(response, "content", None)
        if raw_content is None:
            raw_content = str(getattr(response, "text", "")).encode("utf-8")
        if isinstance(raw_content, bytes):
            content = raw_content.decode("utf-8-sig", errors="replace")
        else:
            content = str(raw_content)
        reader = csv.DictReader(io.StringIO(content))
        retrieved_at = datetime.now(timezone.utc).isoformat()
        observations: list[GlobalObservation] = []
        for row in reader:
            raw_date = str(row.get("observation_date") or "").strip()
            raw_value = str(row.get(source_id) or "").strip()
            if not raw_date or raw_value in {"", ".", "NA", "N/A"}:
                continue
            try:
                parsed = date.fromisoformat(raw_date)
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            observations.append(
                GlobalObservation(
                    series=series,
                    source_id=source_id,
                    observation_date=parsed.isoformat(),
                    value=value,
                    retrieved_at=retrieved_at,
                )
            )
        return observations

    def fetch_missing(
        self,
        series: str,
        missing_dates: Iterable[date],
    ) -> list[GlobalObservation]:
        dates = sorted(set(missing_dates))
        if not dates:
            return []
        # One bounded request covers the gap range; local deduplication ensures
        # only requested dates are persisted.
        observations = self.fetch_series(
            series, start_date=dates[0], end_date=dates[-1]
        )
        wanted = {d.isoformat() for d in dates}
        return [item for item in observations if item.observation_date in wanted]


class GlobalMarketArchive:
    """JSON archive with date-level incremental updates and provenance."""

    def __init__(
        self,
        root: str | Path = "runtime/global_market",
        *,
        client: FREDClient | None = None,
    ) -> None:
        self.root = Path(root)
        self.client = client or FREDClient()

    def _path(self, series: str) -> Path:
        return self.root / f"{series}.json"

    def load(self, series: str) -> dict[str, Any]:
        path = self._path(series)
        if not path.exists():
            return {
                "schema_version": "1.0",
                "series": series,
                "source": "FRED",
                "source_id": self.client.series_map.get(series, series),
                "observations": {},
                "unavailable_dates": {},
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "schema_version": "1.0",
                "series": series,
                "source": "FRED",
                "source_id": self.client.series_map.get(series, series),
                "observations": {},
                "unavailable_dates": {},
            }
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid global archive: {path}")
        payload.setdefault("observations", {})
        payload.setdefault("unavailable_dates", {})
        return payload

    def sync(
        self,
        series: str,
        *,
        start_date: date,
        end_date: date | None = None,
        dry_run: bool = False,
        weekdays_only: bool = True,
        retry_unavailable: bool = False,
    ) -> dict[str, Any]:
        end_date = end_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")
        payload = self.load(series)
        observations = payload.setdefault("observations", {})
        unavailable = payload.setdefault("unavailable_dates", {})
        all_dates = (
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        )
        expected_dates = {
            value.isoformat()
            for value in all_dates
            if not weekdays_only or value.weekday() < 5
        }
        observed_before = set(observations)
        unavailable_before = set(unavailable)
        missing = sorted(
            expected_dates
            - observed_before
            - (unavailable_before if not retry_unavailable else set())
        )
        fetched: list[GlobalObservation] = []
        fetch_error: str | None = None
        if missing and not dry_run:
            try:
                fetched = self.client.fetch_missing(
                    series, [date.fromisoformat(value) for value in missing]
                )
                fetched_dates = {item.observation_date for item in fetched}
                for item in fetched:
                    observations[item.observation_date] = item.as_dict()
                    unavailable.pop(item.observation_date, None)
                # A valid provider response can omit exchange holidays or
                # other non-observation dates.  Record that fact explicitly so
                # the next run does not hammer the same endpoint forever.
                for value in set(missing) - fetched_dates:
                    unavailable[value] = {
                        "reason": "provider_no_observation",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception as exc:
                fetch_error = f"{type(exc).__name__}: {exc}"
        updated_at = datetime.now(timezone.utc).isoformat()
        payload.update(
            {
                "schema_version": "1.0",
                "series": series,
                "source": "FRED",
                "source_id": self.client.series_map.get(series, series),
                "description": SERIES_DESCRIPTIONS.get(series, ""),
                "updated_at": updated_at,
                "requested_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "record_count": len(observations),
                "unavailable_count": len(unavailable),
            }
        )
        path = self._path(series)
        if not dry_run:
            self.root.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "series": series,
            "source": "FRED",
            "source_id": self.client.series_map.get(series, series),
            # FRED series legitimately omit exchange holidays.  Those dates
            # are persisted as provider gaps instead of being forward-filled.
            "status": (
                "DRY_RUN"
                if dry_run
                else "PARTIAL"
                if fetch_error
                or (
                    set(missing)
                    - set(item.observation_date for item in fetched)
                )
                else "COMPLETE"
            ),
            "requested_dates": len(expected_dates),
            "existing_dates": len(expected_dates & observed_before),
            "unavailable_before_fetch": len(expected_dates & unavailable_before),
            "missing_before_fetch": len(missing),
            "fetched_dates": len(fetched),
            "provider_unavailable_dates": sorted(set(missing) - set(item.observation_date for item in fetched)),
            "remaining_missing": sorted(expected_dates - set(observations) - set(unavailable)),
            "archive_path": str(path) if not dry_run else None,
            "dry_run": dry_run,
            "fetch_error": fetch_error,
            "retry_unavailable": retry_unavailable,
            "updated_at": updated_at,
        }

    def sync_many(
        self,
        series: Iterable[str] | None = None,
        *,
        start_date: date,
        end_date: date | None = None,
        dry_run: bool = False,
        weekdays_only: bool = True,
        retry_unavailable: bool = False,
    ) -> dict[str, Any]:
        """Synchronize several registered series and return one run report."""

        names = list(series or self.client.series_map)
        results: dict[str, Any] = {}
        for name in names:
            results[name] = self.sync(
                name,
                start_date=start_date,
                end_date=end_date,
                dry_run=dry_run,
                weekdays_only=weekdays_only,
                retry_unavailable=retry_unavailable,
            )
        return {
            "source": "FRED",
            "series": names,
            "results": results,
            "status": "COMPLETE"
            if all(item["status"] == "COMPLETE" for item in results.values())
            else "PARTIAL",
        }


__all__ = [
    "DEFAULT_SERIES",
    "FREDClient",
    "FRED_CSV_URL",
    "GlobalMarketArchive",
    "GlobalObservation",
    "SERIES_DESCRIPTIONS",
]
