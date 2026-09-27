"""Point-in-time source checks before emitting dependent market conclusions."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from math import isfinite
from typing import Any

from .archive import deduplicate_rows, parse_market_date
from persiantools.jdatetime import JalaliDate
import re


def observed(value: float | int | None, *, unit: str, source: str, source_date: str,
             document_id: str | None = None, locator: str | None = None) -> dict[str, Any]:
    if value is not None and (isinstance(value, bool) or not isfinite(float(value))):
        raise ValueError("Observed metric must be finite and non-boolean")
    return {"value": value, "unit": unit, "source": source,
            "source_document_id": document_id, "source_date": source_date,
            "locator": locator, "calculated": False, "formula": None,
            "data_quality": "HIGH" if value is not None else "UNAVAILABLE"}


def calculated(value: float | int | None, *, unit: str, formula: str,
               inputs: list[dict[str, Any]]) -> dict[str, Any]:
    if not inputs or any(not isinstance(item, dict) or item.get("value") is None
                         or item.get("source_date") is None for item in inputs):
        raise ValueError("Calculated metric requires observed, dated inputs")
    if value is not None and (isinstance(value, bool) or not isfinite(float(value))):
        raise ValueError("Calculated metric must be finite and non-boolean")
    return {"value": value, "unit": unit, "calculated": True, "formula": formula,
            "inputs": inputs, "source_dates": sorted({item["source_date"] for item in inputs}),
            "data_quality": "HIGH" if value is not None else "UNAVAILABLE"}


def market_gate(rows: list[dict[str, Any]], *, symbol: str, as_of: date | None = None,
                max_age_days: int = 5) -> dict[str, Any]:
    """Audit raw observations; exclude invalid rows only in downstream engines.

    A missing latest candle or a date after as_of blocks current conclusions.
    Historical non-trading days are kept in the audit, never filled with prices.
    """
    as_of = as_of or date.today()
    if max_age_days < 0:
        raise ValueError("max_age_days must be nonnegative")
    canonical, dedup = deduplicate_rows(rows, symbol=symbol)
    valid, invalid, missing_volume, future = [], [], [], []
    for item in canonical:
        day = date.fromisoformat(item["source_date"])
        if day > as_of:
            future.append(item["source_date"])
            continue
        values = [item.get(key) for key in ("open", "high", "low", "close")]
        if any(v is None or not isinstance(v, (int, float)) or not isfinite(v)
               or v <= 0 for v in values):
            invalid.append(item["source_date"])
            continue
        open_, high, low, close = values
        if not low <= min(open_, close) <= max(open_, close) <= high:
            invalid.append(item["source_date"])
            continue
        volume = item.get("volume")
        if volume is None or not isinstance(volume, (int, float)) or not isfinite(volume) or volume < 0:
            missing_volume.append(item["source_date"])
            continue
        valid.append(item)
    source_last = canonical[-1]["source_date"] if canonical else None
    latest = valid[-1]["source_date"] if valid else None
    age = (as_of - date.fromisoformat(latest)).days if latest else None
    fresh = age is not None and 0 <= age <= max_age_days
    latest_verified = source_last == latest and bool(latest)
    blockers = []
    if not latest_verified:
        blockers.append("latest_bar_invalid_or_future")
    if len(valid) < 22:
        blockers.append("fewer_than_22_verified_bars")
    if not fresh:
        blockers.append("source_stale_or_unavailable")
    if future:
        blockers.append("future_dated_source_rows")
    status = ("INVALID" if not valid or future or not latest_verified else
              "DEGRADED" if blockers or invalid or missing_volume or dedup["invalid_rows"]
              or dedup["duplicate_dates"] else "MEDIUM")
    # Without an independently verified adjustment history we cannot assert HIGH.
    serial = json.dumps([r["source_row_hash"] for r in valid], sort_keys=True).encode("utf-8")
    return {"status": status, "as_of": as_of.isoformat(), "source": "TSETMC",
            "symbol": symbol, "source_rows": len(rows), "dated_rows": len(canonical),
            "valid_ohlcv_rows": len(valid), "invalid_source_dates": dedup["invalid_rows"],
            "duplicate_dates": dedup["duplicate_date_values"],
            "invalid_ohlc_dates": invalid, "missing_volume_dates": missing_volume,
            "future_dates": future, "latest_source_date": source_last,
            "latest_valid_date": latest, "latest_bar_verified": latest_verified,
            "age_calendar_days": age, "freshness": "FRESH" if fresh else "STALE",
            "corporate_action_adjustment": "UNVERIFIED", "blockers": blockers,
            "valid_rows_sha256": hashlib.sha256(serial).hexdigest(),
            "point_in_time": True}


def source_date_cutoff(value: str, *, as_of: date) -> bool:
    """A source observation is usable only when its publication date is known."""
    parsed = publication_date(value)
    return parsed is not None and parsed <= as_of


def publication_date(value: str | None) -> date | None:
    """Convert explicit Codal Jalali dates; never confuse year 1405 with Gregorian."""
    raw = str(value or "")[:10].translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    matched = re.fullmatch(r"(1[34]\d{2})[/\-](\d{1,2})[/\-](\d{1,2})", raw)
    if matched:
        try:
            return JalaliDate(*map(int, matched.groups())).to_gregorian()
        except ValueError:
            return None
    parsed = parse_market_date(raw)
    return parsed if parsed is not None and 1900 <= parsed.year <= 2100 else None


def financial_gate(reports: list[dict[str, Any]], sync: dict[str, Any] | None,
                   *, instrument_type: str, as_of: date | None = None) -> dict[str, Any]:
    """Describe available Codal evidence before scoring; never assume NAV.

    Persian-calendar publication timestamps need an independently verified
    converter before a historical as-of replay can use those documents.
    """
    as_of = as_of or date.today()
    sync = sync or {}
    annual = [r for r in reports if r.get("report_type") == "annual"]
    periods = {str(r.get("period", ""))[:4] for r in annual}
    latest = max(annual, key=lambda r: r.get("period", "")) if annual else None
    future = []
    unverified_publication = []
    for report in reports:
        published = str(report.get("source_date") or "")
        parsed = publication_date(published)
        if parsed is None:
            unverified_publication.append(str(report.get("document_id") or "unknown"))
        elif parsed > as_of:
            future.append(str(report.get("document_id") or "unknown"))
    failures = sync.get("rejected") or []
    source_status = ("RATE_LIMITED" if any("429" in str(x.get("error", ""))
                                          for x in failures if isinstance(x, dict)) else
                     "PARTIAL" if sync.get("status") in {"PARTIAL", "SOURCE_UNAVAILABLE"} else
                     "SUCCESS" if sync.get("status") == "SUCCESS" else "UNAVAILABLE")
    blockers = []
    if future:
        blockers.append("future_publication")
    if len(periods) < 5:
        blockers.append("fewer_than_five_annual_periods")
    if source_status != "SUCCESS":
        blockers.append("codal_source_partial")
    if unverified_publication:
        blockers.append("publication_calendar_unverified")
    status = "INVALID" if future else "DEGRADED" if blockers else "MEDIUM"
    return {"status": status, "source": "KODAL", "instrument_type": instrument_type,
            "as_of": as_of.isoformat(), "annual_periods": sorted(periods),
            "annual_report_count": len(annual), "latest_document_id":
            latest.get("document_id") if latest else None,
            "latest_period": latest.get("period") if latest else None,
            "latest_audited": latest.get("audited") if latest else None,
            "latest_publication_date": latest.get("source_date") if latest else None,
            "source_status": source_status, "rejected_count": len(failures),
            "future_document_ids": future,
            "unverified_publication_document_ids": unverified_publication,
            "blockers": blockers, "point_in_time": not bool(future or unverified_publication)}
