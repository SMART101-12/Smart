"""Deterministic contract for SMART's point-in-time symbol analysis.

Local code calculates facts and validates the snapshot. The optional LLM layer
can explain this sealed contract, but is never allowed to invent missing data,
replace numeric signals, or access future rows.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Iterable, Mapping


ANALYSIS_SCHEMA_VERSION = "analysis-contract-v1"
ALLOWED_LABELS = {"bullish", "bearish", "neutral", "watchlist", "high-risk"}
ALLOWED_PHASES = {"accumulation", "growth", "distribution", "correction", "decline", "neutral", "unknown"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "very_high", "unknown"}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _number_from(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        result = _number(row.get(key))
        if result is not None:
            return result
    return None


def _date_from(value: Any) -> date | None:
    raw = str(value or "").strip().replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _normalise_rows(value: Any) -> list[Mapping[str, Any]]:
    """Return only row mappings from one of the supported snapshot layouts."""

    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _history_from_snapshot(
    snapshot: Mapping[str, Any], analysis: Mapping[str, Any]
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    """Accept live, V2 and test snapshots without guessing missing values."""

    candidates: list[Any] = [
        analysis.get("technical_history"),
        snapshot.get("technical_history"),
        analysis.get("history"),
        snapshot.get("history"),
        snapshot.get("bars"),
    ]
    for candidate in candidates:
        latest: Mapping[str, Any] = {}
        rows: list[Mapping[str, Any]] = []
        if isinstance(candidate, Mapping):
            latest_value = candidate.get("latest")
            if isinstance(latest_value, Mapping):
                latest = latest_value
            rows = _normalise_rows(
                candidate.get("history")
                or candidate.get("rows")
                or candidate.get("bars")
            )
        else:
            rows = _normalise_rows(candidate)
        if rows:
            return rows, latest or rows[-1]
    latest_value = analysis.get("latest") or snapshot.get("latest")
    return [], latest_value if isinstance(latest_value, Mapping) else {}


def _quality(rows: list[Mapping[str, Any]], as_of: str | None) -> dict[str, Any]:
    issues: list[str] = []
    if not rows:
        issues.append("no_ohlcv_rows")
    elif len(rows) < 20:
        issues.append("short_history")
    dates = [_date_from(row.get("date") or row.get("dEven") or row.get("source_date")) for row in rows]
    valid_dates = [item for item in dates if item is not None]
    if len(valid_dates) != len(rows):
        issues.append("invalid_dates")
    if valid_dates and valid_dates != sorted(valid_dates):
        issues.append("dates_not_ascending")
    if len(set(valid_dates)) != len(valid_dates):
        issues.append("duplicate_dates")
    aliases = {
        "open": ("open", "pFirst"),
        "high": ("high", "pMax"),
        "low": ("low", "pMin"),
        "close": ("close", "pClosing", "pDrCotVal"),
        "volume": ("volume", "qTotTran5J"),
    }
    for field, names in aliases.items():
        missing = sum(_number_from(row, *names) is None for row in rows)
        if missing:
            issues.append(f"missing_{field}:{missing}")
    canonical_as_of = str(as_of or "").replace("-", "").replace("/", "")
    if canonical_as_of and valid_dates and max(valid_dates).strftime("%Y%m%d") != canonical_as_of:
        issues.append("as_of_does_not_match_latest_row")
    status = (
        "poor"
        if not rows or "no_ohlcv_rows" in issues
        else "good"
        if not issues
        else "medium"
        if len(issues) <= 2
        else "poor"
    )
    return {"status": status, "issues": issues, "rows": len(rows)}


def _trend(price: float | None, fast: float | None, slow: float | None) -> str:
    if None in (price, fast, slow):
        return "unknown"
    if price > fast > slow:
        return "bullish"
    if price < fast < slow:
        return "bearish"
    return "neutral"


def _support_resistance(rows: list[Mapping[str, Any]], price: float | None) -> dict[str, list[float]]:
    closes = [
        value
        for row in rows
        for value in [_number_from(row, "close", "pClosing", "pDrCotVal")]
        if value is not None and value > 0
    ]
    if price is None or not closes:
        return {"supports": [], "resistances": []}
    window = closes[-60:]
    supports = sorted({round(value, 6) for value in window if value < price}, reverse=True)
    resistances = sorted({round(value, 6) for value in window if value > price})
    return {"supports": supports[:3], "resistances": resistances[:3]}


def _phase(snapshot: Mapping[str, Any], price: float | None, sma20: float | None, sma50: float | None) -> str:
    smart = snapshot.get("smart_money")
    smart = smart if isinstance(smart, Mapping) else {}
    raw = str(smart.get("phase") or "").lower()
    if "accum" in raw:
        return "accumulation"
    if "trend" in raw or "growth" in raw:
        return "growth"
    if "distrib" in raw:
        return "distribution"
    if "decline" in raw or "bear" in raw:
        return "decline"
    if "correction" in raw:
        return "correction"
    trend = _trend(price, sma20, sma50)
    return "growth" if trend == "bullish" else "neutral" if raw else "unknown"


def _long_term_label(value: Any) -> str:
    """Normalize legacy BUY/HOLD/SELL decisions to trend vocabulary."""

    raw = str(value or "").strip().lower()
    if raw in {"buy", "bullish", "positive", "positive_watch"}:
        return "bullish"
    if raw in {"sell", "bearish", "negative", "negative_watch"}:
        return "bearish"
    if raw in {"hold", "neutral", "neutral_watch"}:
        return "neutral"
    return "unknown"


def _volume_status(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio >= 1.2:
        return "above_average"
    if ratio <= 0.8:
        return "below_average"
    return "normal"


def _risk(snapshot: Mapping[str, Any], quality: Mapping[str, Any], price: float | None, atr: float | None, rsi: float | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if atr is not None and price and atr / price >= 0.08:
        reasons.append("high_volatility")
    if rsi is not None and rsi > 75:
        reasons.append("overbought_momentum")
    if quality.get("status") == "poor":
        reasons.append("poor_data_quality")
    elif quality.get("status") == "medium":
        reasons.append("degraded_data_quality")
    smart = snapshot.get("smart_money")
    phase = str((smart or {}).get("phase") or "").lower() if isinstance(smart, Mapping) else ""
    if phase in {"distribution_or_unconfirmed", "watch"}:
        reasons.append("unconfirmed_money_flow")
    if not reasons:
        return "low", reasons
    if "poor_data_quality" in reasons or len(reasons) >= 3:
        return "very_high", reasons
    return ("high" if len(reasons) == 2 else "medium"), reasons


def build_structured_analysis(snapshot: Mapping[str, Any], *, previous_outcomes: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Produce a fail-closed, machine-readable analysis for one snapshot."""
    analysis = snapshot.get("analysis")
    analysis = analysis if isinstance(analysis, Mapping) else snapshot
    context = dict(analysis)
    context.update(snapshot)
    history, latest = _history_from_snapshot(snapshot, analysis)
    symbol = str(snapshot.get("symbol") or analysis.get("symbol") or "")
    as_of = str(analysis.get("as_of") or latest.get("date") or snapshot.get("as_of") or "")
    quality = _quality(history, as_of or None)
    upstream_quality = analysis.get("data_quality")
    if isinstance(upstream_quality, Mapping) and upstream_quality.get("status") in {"DEGRADED", "medium", "poor"} and quality["status"] == "good":
        quality["status"] = "medium"
        quality["issues"].append("upstream_quality_degraded")
    upstream_score = _number(upstream_quality)
    if upstream_score is None:
        upstream_score = _number(snapshot.get("data_quality"))
    if upstream_score is not None:
        if upstream_score < 50:
            quality["status"] = "poor"
            quality["issues"].append("upstream_quality_low")
        elif upstream_score < 80 and quality["status"] == "good":
            quality["status"] = "medium"
            quality["issues"].append("upstream_quality_medium")
    price = _number(snapshot.get("price")) or _number(latest.get("close"))
    rsi = _number_from(latest, "rsi14", "rsi")
    macd = _number(latest.get("macd"))
    macd_signal = _number(latest.get("macd_signal"))
    sma20 = _number_from(latest, "sma20", "sma_slow")
    sma50 = _number_from(latest, "sma50", "sma_slow")
    ema12 = _number_from(latest, "ema12", "ema_fast")
    ema26 = _number_from(latest, "ema26", "ema_slow")
    atr = _number_from(latest, "atr14", "atr")
    volume_ratio = _number_from(latest, "volume_ratio20", "volume_ratio")
    momentum_bits: list[str] = []
    if rsi is not None:
        momentum_bits.append("overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral-to-positive" if rsi >= 50 else "weak")
    if macd is not None and macd_signal is not None:
        momentum_bits.append("MACD above signal" if macd > macd_signal else "MACD below signal")
    levels = _support_resistance(history, price)
    phase = _phase(context, price, sma20, sma50)
    risk_level, risk_reasons = _risk(context, quality, price, atr, rsi)
    engine = analysis.get("factor_engine")
    engine = engine if isinstance(engine, Mapping) else {}
    score = _number(engine.get("composite"))
    score = max(0.0, min(100.0, score if score is not None else 50.0))
    confidence = max(0.0, min(100.0, 100.0 - 15.0 * len(quality["issues"])))
    if phase == "unknown" or not history:
        confidence = min(confidence, 35.0)
    if all(value is None for value in (rsi, macd, macd_signal, sma20, sma50, ema12, ema26)):
        confidence = min(confidence, 40.0)
    label = (
        "watchlist"
        if quality["status"] == "poor" or not history or confidence < 45.0
        else "high-risk"
        if risk_level == "very_high"
        else "bullish"
        if score >= 65
        else "bearish"
        if score <= 35
        else "watchlist"
        if score >= 55
        else "neutral"
    )
    smart = context.get("smart_money")
    smart = smart if isinstance(smart, Mapping) else {}
    supports, resistances = levels["supports"], levels["resistances"]
    warnings = list(quality["issues"])
    warnings.extend(["historical results do not guarantee future performance", "research decision-support only; no order is placed"])
    flow_value = _number(snapshot.get("retail_net_volume"))
    if flow_value is None:
        flow_value = _number(analysis.get("retail_net_volume"))
    smart_hint = smart.get("phase")
    smart_hint = str(smart_hint) if smart_hint not in (None, "") else None
    outcome_values = list(previous_outcomes or [])
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "symbol": symbol,
        "as_of": as_of or None,
        "data_quality": quality,
        "trend": {"short_term": _trend(price, sma20, sma50), "mid_term": _trend(price, ema12, ema26), "long_term": _long_term_label(engine.get("decision"))},
        "momentum": {"rsi": rsi, "macd": macd, "macd_signal": macd_signal, "interpretation": "; ".join(momentum_bits) or "insufficient data"},
        "volume_flow": {"volume_status": _volume_status(volume_ratio), "real_money_flow": flow_value, "smart_money_hint": smart_hint},
        "market_phase": phase,
        "support_resistance": levels,
        "risk": {"level": risk_level, "reasons": risk_reasons},
        "scenarios": [
            {"name": "bullish", "condition": f"close above {resistances[0]}" if resistances else "confirmed breakout with above-average volume", "outlook": "trend continuation needs price and volume confirmation"},
            {"name": "bearish", "condition": f"close below {supports[0]}" if supports else "loss of the latest swing low", "outlook": "downside risk increases; reassess rather than average blindly"},
            {"name": "neutral", "condition": "price remains between the nearest confirmed support and resistance", "outlook": "wait for a confirmed break or a lower-risk pullback"},
        ],
        "final_assessment": {"score_0_100": round(score, 4), "confidence_0_100": round(confidence, 4), "label": label, "summary": f"{symbol or 'symbol'}: {label}; evidence ends at {as_of or 'the latest available date'}."},
        "actionable_notes": ["Confirm price and volume behavior in the next validated observation.", "This is not an execution order; reassess after each new snapshot."],
        "warning": warnings,
        "provenance": {"point_in_time": True, "future_rows_used_for_current_signal": False, "previous_outcomes_count": len(outcome_values)},
    }


def validate_structured_analysis(payload: Mapping[str, Any]) -> list[str]:
    """Return contract violations; an empty list is a valid result."""
    required = {"schema_version", "symbol", "data_quality", "trend", "momentum", "volume_flow", "market_phase", "support_resistance", "risk", "scenarios", "final_assessment", "actionable_notes", "warning", "provenance"}
    errors = [f"missing:{key}" for key in sorted(required - set(payload))]
    if payload.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        errors.append("invalid:schema_version")
    quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), Mapping) else {}
    if quality.get("status") not in {"good", "medium", "poor"}:
        errors.append("invalid:data_quality.status")
    trend = payload.get("trend") if isinstance(payload.get("trend"), Mapping) else {}
    for key in ("short_term", "mid_term", "long_term"):
        if trend.get(key) not in {"bullish", "bearish", "neutral", "unknown"}:
            errors.append(f"invalid:trend.{key}")
    momentum = payload.get("momentum") if isinstance(payload.get("momentum"), Mapping) else {}
    for key in ("rsi", "macd", "macd_signal"):
        if momentum.get(key) is not None and _number(momentum.get(key)) is None:
            errors.append(f"invalid:momentum.{key}")
    if payload.get("market_phase") not in ALLOWED_PHASES:
        errors.append("invalid:market_phase")
    risk = payload.get("risk") if isinstance(payload.get("risk"), Mapping) else {}
    if risk.get("level") not in ALLOWED_RISK_LEVELS:
        errors.append("invalid:risk.level")
    final = payload.get("final_assessment") if isinstance(payload.get("final_assessment"), Mapping) else {}
    if final.get("label") not in ALLOWED_LABELS:
        errors.append("invalid:final_assessment.label")
    for key in ("score_0_100", "confidence_0_100"):
        value = _number(final.get(key))
        if value is None or not 0 <= value <= 100:
            errors.append(f"invalid:final_assessment.{key}")
    scenarios = payload.get("scenarios")
    names = {item.get("name") for item in scenarios if isinstance(item, Mapping)} if isinstance(scenarios, list) else set()
    if names < {"bullish", "bearish", "neutral"}:
        errors.append("invalid:scenarios")
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), Mapping) else {}
    if provenance.get("point_in_time") is not True:
        errors.append("invalid:provenance.point_in_time")
    if provenance.get("future_rows_used_for_current_signal") is not False:
        errors.append("invalid:provenance.future_rows_used_for_current_signal")
    return errors


def analysis_json_schema() -> dict[str, Any]:
    """Structured-output schema used by the optional OpenAI explanation call."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "symbol", "as_of", "data_quality", "trend", "momentum", "volume_flow", "market_phase", "support_resistance", "risk", "scenarios", "final_assessment", "actionable_notes", "warning", "provenance"],
        "properties": {
            "schema_version": {"type": "string", "enum": [ANALYSIS_SCHEMA_VERSION]},
            "symbol": {"type": "string"},
            "as_of": {"type": ["string", "null"]},
            "data_quality": {"type": "object", "additionalProperties": False, "required": ["status", "issues"], "properties": {"status": {"type": "string", "enum": ["good", "medium", "poor"]}, "issues": {"type": "array", "items": {"type": "string"}}}},
            "trend": {"type": "object", "additionalProperties": False, "required": ["short_term", "mid_term", "long_term"], "properties": {"short_term": {"type": "string"}, "mid_term": {"type": "string"}, "long_term": {"type": "string"}}},
            "momentum": {"type": "object", "additionalProperties": False, "required": ["rsi", "macd", "macd_signal", "interpretation"], "properties": {"rsi": {"type": ["number", "null"]}, "macd": {"type": ["number", "null"]}, "macd_signal": {"type": ["number", "null"]}, "interpretation": {"type": "string"}}},
            "volume_flow": {"type": "object", "additionalProperties": False, "required": ["volume_status", "real_money_flow", "smart_money_hint"], "properties": {"volume_status": {"type": "string"}, "real_money_flow": {"type": ["number", "null"]}, "smart_money_hint": {"type": ["string", "null"]}}},
            "market_phase": {"type": "string", "enum": sorted(ALLOWED_PHASES)},
            "support_resistance": {"type": "object", "additionalProperties": False, "required": ["supports", "resistances"], "properties": {"supports": {"type": "array", "items": {"type": "number"}}, "resistances": {"type": "array", "items": {"type": "number"}}}},
            "risk": {"type": "object", "additionalProperties": False, "required": ["level", "reasons"], "properties": {"level": {"type": "string", "enum": sorted(ALLOWED_RISK_LEVELS)}, "reasons": {"type": "array", "items": {"type": "string"}}}},
            "scenarios": {"type": "array", "minItems": 3, "items": {"type": "object", "additionalProperties": False, "required": ["name", "condition", "outlook"], "properties": {"name": {"type": "string", "enum": ["bullish", "bearish", "neutral"]}, "condition": {"type": "string"}, "outlook": {"type": "string"}}}},
            "final_assessment": {"type": "object", "additionalProperties": False, "required": ["score_0_100", "confidence_0_100", "label", "summary"], "properties": {"score_0_100": {"type": "number", "minimum": 0, "maximum": 100}, "confidence_0_100": {"type": "number", "minimum": 0, "maximum": 100}, "label": {"type": "string", "enum": sorted(ALLOWED_LABELS)}, "summary": {"type": "string"}}},
            "actionable_notes": {"type": "array", "items": {"type": "string"}},
            "warning": {"type": "array", "items": {"type": "string"}},
            "provenance": {"type": "object", "additionalProperties": False, "required": ["point_in_time", "future_rows_used_for_current_signal", "previous_outcomes_count"], "properties": {"point_in_time": {"type": "boolean", "enum": [True]}, "future_rows_used_for_current_signal": {"type": "boolean", "enum": [False]}, "previous_outcomes_count": {"type": "integer", "minimum": 0}}},
        },
    }


__all__ = ["ANALYSIS_SCHEMA_VERSION", "analysis_json_schema", "build_structured_analysis", "validate_structured_analysis"]
