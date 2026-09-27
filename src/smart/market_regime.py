"""Dated Iranian market and industry context; missing evidence stays unknown.

The optional SMART_REGIME_SNAPSHOT JSON is an imported evidence bundle. Its
declared provenance is shown to the reader, never independently authenticated.
"""
from __future__ import annotations

import json
import os
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any


def _day(value: Any) -> date | None:
    try:
        result = date.fromisoformat(str(value))
        return result if 1900 <= result.year <= 2100 else None
    except (ValueError, TypeError):
        return None


def _series(rows: Any, cutoff: date, *, source: str | None,
            max_age_days: int = 5) -> tuple[list[tuple[date, float]], list[str]]:
    if not source or not isinstance(rows, list):
        return [], ["dated_source_unavailable"]
    values: dict[date, float] = {}
    errors: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append("invalid_observation")
            continue
        day = _day(row.get("date"))
        value = row.get("close")
        if day is None or type(value) not in (int, float) or not isfinite(value) or value <= 0:
            errors.append("invalid_observation")
        elif day > cutoff:
            errors.append("future_observation_excluded")
        elif day in values:
            errors.append("duplicate_observation")
        else:
            values[day] = float(value)
    ordered = sorted(values.items())
    if len(ordered) < 22:
        errors.append("fewer_than_22_observations")
    if not ordered or (cutoff - ordered[-1][0]).days > max_age_days:
        errors.append("stale_or_missing_latest_observation")
    return ordered, sorted(set(errors))


def _change(values: list[tuple[date, float]], periods: int = 20) -> float:
    return round(100 * (values[-1][1] / values[-periods - 1][1] - 1), 3)


def analyze_market_regime(bundle: dict[str, Any] | None, *, as_of: date) -> dict[str, Any]:
    """Classify broad market using two independent dated Iranian index series."""
    bundle = bundle or {}
    source = bundle.get("source")
    major, major_errors = _series(bundle.get("major_index"), as_of, source=source)
    equal, equal_errors = _series(bundle.get("equal_weight_index"), as_of, source=source)
    errors = sorted(set(major_errors + equal_errors))
    result = {"status": "UNAVAILABLE", "regime": "UNKNOWN", "as_of": None,
              "source": source, "errors": errors, "evidence": {}, "conflicts": []}
    if errors:
        return result
    # Both indices must describe the same market session.
    if major[-1][0] != equal[-1][0]:
        result["errors"].append("index_dates_not_aligned")
        return result
    m, e = _change(major), _change(equal)
    conflicts = ["major_equal_weight_divergence"] if m * e < 0 else []
    regime = ("RISK_OFF" if m <= -8 and e <= -8 else
              "BULL" if m >= 3 and e >= 3 else
              "BEAR" if m <= -3 and e <= -3 else
              "SIDEWAYS" if abs(m) < 2 and abs(e) < 2 else "NEUTRAL")
    return {**result, "status": "SUCCESS", "regime": regime,
            "as_of": major[-1][0].isoformat(), "errors": [],
            "evidence": {"major_20_session_change_pct": m,
                         "equal_weight_20_session_change_pct": e,
                         "major_last": major[-1][1], "equal_weight_last": equal[-1][1]},
            "conflicts": conflicts}


def analyze_industry_regime(bundle: dict[str, Any] | None, *, symbol: str,
                            as_of: date) -> dict[str, Any]:
    """Use membership valid at as_of, never today's sector for a past date."""
    bundle = bundle or {}
    result = {"status": "UNAVAILABLE", "regime": "UNKNOWN", "as_of": None,
              "industry": None, "source": bundle.get("source"), "errors": [],
              "evidence": {}, "conflicts": []}
    memberships = bundle.get("memberships") or []
    matched = [r for r in memberships if isinstance(r, dict) and r.get("symbol") == symbol
               and _day(r.get("effective_from")) is not None
               and _day(r["effective_from"]) <= as_of
               and (r.get("effective_to") is None or
                    (_day(r["effective_to"]) is not None and _day(r["effective_to"]) >= as_of))]
    if len(matched) != 1 or not bundle.get("source"):
        result["errors"] = ["historical_industry_membership_unavailable_or_ambiguous"]
        return result
    industry = matched[0].get("industry")
    row = (bundle.get("industry_indices") or {}).get(industry)
    series, errors = _series(row, as_of, source=bundle.get("source"))
    result.update(industry=industry, errors=errors)
    if errors:
        return result
    change = _change(series)
    regime = "BULL" if change >= 3 else "BEAR" if change <= -3 else "NEUTRAL"
    result.update(status="SUCCESS", regime=regime, as_of=series[-1][0].isoformat(),
                  evidence={"industry_20_session_change_pct": change,
                            "membership_effective_from": matched[0]["effective_from"],
                            "membership_effective_to": matched[0].get("effective_to")})
    return result


def load_regime_snapshot() -> dict[str, Any]:
    """Optional operator-imported bundle; no implicit substitute from symbol prices."""
    path = os.getenv("SMART_REGIME_SNAPSHOT")
    if not path:
        return {}
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError("Market regime snapshot must be an object")
    return snapshot
