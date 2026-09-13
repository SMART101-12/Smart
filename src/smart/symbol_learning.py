"""Per-symbol adaptive, multi-timeframe, long-only entry research.

This module is intentionally separate from the broad 200-strategy catalog.
It learns a different indicator-weight profile for each symbol, uses only
information available at the end of each trading day, and evaluates only
long-entry candidates.  It does *not* place orders or promise profitability.

The research protocol is deliberately conservative:

* daily decisions are made at the close and enter at the next open;
* higher-timeframe indicators use the previous completed bucket;
* indicator weights are updated only when a prior simulated trade closes;
* candidate selection uses validation metrics only; the final test range is
  kept separate and is never used to choose a candidate;
* every entry, win, loss, rejected reason and weight update is persisted per
  symbol for later review.
"""
from __future__ import annotations

import json
import math
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

from .archive import safe_symbol
from .technical_analysis import Bar


FOCUS_SYMBOLS = ("فولاد", "پالایش", "فملی", "فجر")
TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")
INDICATORS = ("ichimoku", "macd", "rsi", "ema", "sma")
ENGINE_VERSION = "symbol-adaptive-entry-v2"

# A candidate needs enough independent, after-cost evidence before it can be
# treated as a research hypothesis or a paper-monitoring candidate.
MIN_VALIDATION_TRADES = 5
MIN_TEST_TRADES = 5
MIN_PROFIT_FACTOR = 1.0
MAX_ACCEPTABLE_DRAWDOWN_PCT = -35.0


@dataclass(frozen=True)
class EntryConfig:
    """One auditable long-only entry configuration in the inner search."""

    config_id: str
    label: str
    mode: str
    threshold: float
    holding_bars: int
    stop_atr: float
    target_atr: float
    learning_rate: float
    min_positive_components: int
    improvement_round: int
    description: str


@dataclass(frozen=True)
class IndicatorState:
    date: str
    close: float
    sma_fast: float | None
    sma_slow: float | None
    ema_fast: float | None
    ema_slow: float | None
    macd: float | None
    macd_signal: float | None
    rsi: float | None
    tenkan: float | None
    kijun: float | None
    span_a: float | None
    span_b: float | None
    cloud_top: float | None
    cloud_bottom: float | None
    atr: float | None
    breakout_up: bool


@dataclass(frozen=True)
class TimeframeData:
    bars: tuple[Bar, ...]
    states: tuple[IndicatorState, ...]
    completed_index_by_daily_bar: tuple[int | None, ...]


_PARAMETERS: dict[str, dict[str, int]] = {
    # Standard daily/weekly parameters.  Monthly parameters are shortened a
    # little so a ten-year study has enough observations.  Annual periods are
    # deliberately scaled: conventional 52-period Ichimoku needs 52 years,
    # which is not realistic for most listed instruments.
    "daily": {
        "sma_fast": 20, "sma_slow": 50, "ema_fast": 12, "ema_slow": 26,
        "macd_signal": 9, "rsi": 14, "tenkan": 9, "kijun": 26,
        "span_b": 52, "atr": 14, "breakout": 20,
    },
    "weekly": {
        "sma_fast": 20, "sma_slow": 50, "ema_fast": 12, "ema_slow": 26,
        "macd_signal": 9, "rsi": 14, "tenkan": 9, "kijun": 26,
        "span_b": 52, "atr": 14, "breakout": 20,
    },
    "monthly": {
        "sma_fast": 9, "sma_slow": 24, "ema_fast": 6, "ema_slow": 13,
        "macd_signal": 5, "rsi": 8, "tenkan": 5, "kijun": 13,
        "span_b": 26, "atr": 8, "breakout": 10,
    },
    "yearly": {
        "sma_fast": 3, "sma_slow": 5, "ema_fast": 2, "ema_slow": 4,
        "macd_signal": 2, "rsi": 3, "tenkan": 2, "kijun": 3,
        "span_b": 5, "atr": 3, "breakout": 3,
    },
}


def _number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, "", "-", ".", "NA", "N/A"):
            continue
        try:
            result = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if math.isfinite(result):
            return result
    return 0.0


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip().replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def normalize_bars(rows: Iterable[dict[str, Any]]) -> list[Bar]:
    """Normalize mixed TSETMC/canonical rows to unique, oldest-first bars."""

    selected: dict[str, Bar] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_date = row.get("dEven") or row.get("date") or row.get("source_date")
        parsed = _parse_date(raw_date)
        if parsed is None:
            continue
        close = _number(row, "pClosing", "close", "priceClosing", "pDrCotVal", "pcl")
        if close <= 0:
            continue
        key = parsed.strftime("%Y%m%d")
        selected[key] = Bar(
            date=key,
            close=close,
            high=_number(row, "pMax", "high", "priceMax", "pClosing") or close,
            low=_number(row, "pMin", "low", "priceMin", "pClosing") or close,
            open=_number(row, "pFirst", "open", "priceFirst", "pClosing") or close,
            volume=_number(row, "qTotTran5J", "volume", "tvol"),
            value=_number(row, "qTotCap", "value", "tval"),
            trades=_number(row, "zTotTran", "trades", "tno"),
        )
    return [selected[key] for key in sorted(selected)]


def _limit_to_years(bars: Sequence[Bar], years: int) -> list[Bar]:
    if years <= 0 or not bars:
        return list(bars)
    end = _parse_date(bars[-1].date)
    if end is None:
        return list(bars)
    try:
        cutoff = end.replace(year=end.year - years)
    except ValueError:  # February 29
        cutoff = end.replace(year=end.year - years, day=28)
    return [bar for bar in bars if (_parse_date(bar.date) or end) >= cutoff]


def _bucket_key(value: date, timeframe: str) -> tuple[int, ...]:
    if timeframe == "weekly":
        year, week, _ = value.isocalendar()
        return year, week
    if timeframe == "monthly":
        return value.year, value.month
    if timeframe == "yearly":
        return (value.year,)
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _aggregate_timeframe(bars: Sequence[Bar], timeframe: str) -> tuple[list[Bar], list[int | None]]:
    """Aggregate daily bars and map each day to a *previous* completed bucket.

    Using the preceding completed weekly/monthly/yearly bucket is deliberately
    conservative: no decision can inspect a partially formed higher-timeframe
    candle that later receives additional observations.
    """

    if timeframe == "daily":
        return list(bars), list(range(len(bars)))
    groups: list[list[int]] = []
    current_key: tuple[int, ...] | None = None
    for index, bar in enumerate(bars):
        parsed = _parse_date(bar.date)
        if parsed is None:
            continue
        key = _bucket_key(parsed, timeframe)
        if key != current_key:
            groups.append([])
            current_key = key
        groups[-1].append(index)

    aggregated: list[Bar] = []
    mapping: list[int | None] = [None] * len(bars)
    for group_index, indices in enumerate(groups):
        if not indices:
            continue
        first, last = indices[0], indices[-1]
        window = [bars[index] for index in indices]
        aggregated.append(
            Bar(
                date=bars[last].date,
                open=bars[first].open,
                high=max(bar.high for bar in window),
                low=min(bar.low for bar in window),
                close=bars[last].close,
                volume=sum(bar.volume for bar in window),
                value=sum(bar.value for bar in window),
                trades=sum(bar.trades for bar in window),
            )
        )
        # The current bucket is never visible as a finished higher-timeframe
        # candle at a daily decision.  The previous bucket is known in full.
        completed = group_index - 1 if group_index else None
        for daily_index in indices:
            mapping[daily_index] = completed
    return aggregated, mapping


def _sma(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            output[index] = running / period
    return output


def _ema(values: Sequence[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    seed: list[float] = []
    current: float | None = None
    alpha = 2.0 / (period + 1.0)
    for index, value in enumerate(values):
        if value is None:
            if current is None:
                seed.clear()
            continue
        if current is None:
            seed.append(float(value))
            if len(seed) == period:
                current = sum(seed) / period
                output[index] = current
            continue
        current = alpha * float(value) + (1.0 - alpha) * current
        output[index] = current
    return output


def _rsi(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output
    gains = [0.0] * len(values)
    losses = [0.0] * len(values)
    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        gains[index] = max(change, 0.0)
        losses[index] = max(-change, 0.0)
    average_gain = sum(gains[1 : period + 1]) / period
    average_loss = sum(losses[1 : period + 1]) / period
    output[period] = 100.0 if average_loss == 0 else 100.0 - 100.0 / (1.0 + average_gain / average_loss)
    for index in range(period + 1, len(values)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
        output[index] = 100.0 if average_loss == 0 else 100.0 - 100.0 / (1.0 + average_gain / average_loss)
    return output


def _atr(bars: Sequence[Bar], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return output
    ranges: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            ranges.append(max(bar.high - bar.low, 0.0))
        else:
            previous = bars[index - 1].close
            ranges.append(max(bar.high - bar.low, abs(bar.high - previous), abs(bar.low - previous)))
    value = sum(ranges[:period]) / period
    output[period - 1] = value
    for index in range(period, len(bars)):
        value = (value * (period - 1) + ranges[index]) / period
        output[index] = value
    return output


def _midpoint(highs: Sequence[float], lows: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(highs)
    for index in range(period - 1, len(highs)):
        output[index] = (max(highs[index - period + 1 : index + 1]) + min(lows[index - period + 1 : index + 1])) / 2.0
    return output


def _indicator_states(bars: Sequence[Bar], timeframe: str) -> list[IndicatorState]:
    params = _PARAMETERS[timeframe]
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    sma_fast = _sma(closes, params["sma_fast"])
    sma_slow = _sma(closes, params["sma_slow"])
    ema_fast = _ema(closes, params["ema_fast"])
    ema_slow = _ema(closes, params["ema_slow"])
    macd = [
        None if fast is None or slow is None else fast - slow
        for fast, slow in zip(ema_fast, ema_slow)
    ]
    macd_signal = _ema(macd, params["macd_signal"])
    rsi = _rsi(closes, params["rsi"])
    atr = _atr(bars, params["atr"])
    tenkan = _midpoint(highs, lows, params["tenkan"])
    kijun = _midpoint(highs, lows, params["kijun"])
    span_b_raw = _midpoint(highs, lows, params["span_b"])
    span_a_raw = [
        None if tenkan[index] is None or kijun[index] is None else (tenkan[index] + kijun[index]) / 2.0
        for index in range(len(bars))
    ]
    output: list[IndicatorState] = []
    for index, bar in enumerate(bars):
        # The projected cloud plotted at time t was calculated `kijun` bars
        # ago.  This use of lagged raw spans keeps the standard chart relation
        # while ensuring that no future candle is ever consulted.
        cloud_index = index - params["kijun"]
        span_a = span_a_raw[cloud_index] if cloud_index >= 0 else None
        span_b = span_b_raw[cloud_index] if cloud_index >= 0 else None
        cloud_top = max(span_a, span_b) if span_a is not None and span_b is not None else None
        cloud_bottom = min(span_a, span_b) if span_a is not None and span_b is not None else None
        prior = closes[max(0, index - params["breakout"]) : index]
        breakout = bool(prior and bar.close > max(prior))
        output.append(
            IndicatorState(
                date=bar.date,
                close=bar.close,
                sma_fast=sma_fast[index],
                sma_slow=sma_slow[index],
                ema_fast=ema_fast[index],
                ema_slow=ema_slow[index],
                macd=macd[index],
                macd_signal=macd_signal[index],
                rsi=rsi[index],
                tenkan=tenkan[index],
                kijun=kijun[index],
                span_a=span_a,
                span_b=span_b,
                cloud_top=cloud_top,
                cloud_bottom=cloud_bottom,
                atr=atr[index],
                breakout_up=breakout,
            )
        )
    return output


def _build_context(bars: Sequence[Bar]) -> dict[str, TimeframeData]:
    context: dict[str, TimeframeData] = {}
    for timeframe in TIMEFRAMES:
        aggregated, mapping = _aggregate_timeframe(bars, timeframe)
        context[timeframe] = TimeframeData(
            bars=tuple(aggregated),
            states=tuple(_indicator_states(aggregated, timeframe)),
            completed_index_by_daily_bar=tuple(mapping),
        )
    return context


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _round(value: float | None, digits: int = 6) -> float | None:
    return round(float(value), digits) if value is not None and math.isfinite(value) else None


def _state_values(state: IndicatorState) -> dict[str, Any]:
    return {
        "date": state.date,
        "close": _round(state.close),
        "sma_fast": _round(state.sma_fast),
        "sma_slow": _round(state.sma_slow),
        "ema_fast": _round(state.ema_fast),
        "ema_slow": _round(state.ema_slow),
        "macd": _round(state.macd),
        "macd_signal": _round(state.macd_signal),
        "rsi": _round(state.rsi, 4),
        "tenkan": _round(state.tenkan),
        "kijun": _round(state.kijun),
        "span_a": _round(state.span_a),
        "span_b": _round(state.span_b),
        "cloud_top": _round(state.cloud_top),
        "cloud_bottom": _round(state.cloud_bottom),
        "atr": _round(state.atr),
        "breakout_up": state.breakout_up,
    }


def _component_scores(state: IndicatorState, previous: IndicatorState | None) -> dict[str, float | None]:
    """Return five signed, point-in-time indicator component scores.

    Positive values support a long entry, negative values veto it, and None
    means the relevant indicator has not warmed up yet.
    """

    if state.sma_fast is None or state.sma_slow is None:
        sma_score = None
    elif state.close > state.sma_fast > state.sma_slow:
        sma_score = 1.0
    elif state.close > state.sma_fast:
        sma_score = 0.45
    elif state.close < state.sma_fast < state.sma_slow:
        sma_score = -1.0
    else:
        sma_score = -0.35

    if state.ema_fast is None or state.ema_slow is None:
        ema_score = None
    elif state.close > state.ema_fast and state.ema_fast > state.ema_slow:
        ema_score = 1.0
    elif state.ema_fast > state.ema_slow:
        ema_score = 0.45
    elif state.close < state.ema_fast and state.ema_fast < state.ema_slow:
        ema_score = -1.0
    else:
        ema_score = -0.35

    if state.macd is None or state.macd_signal is None:
        macd_score = None
    elif state.macd > state.macd_signal and state.macd >= 0:
        macd_score = 1.0
    elif state.macd > state.macd_signal:
        macd_score = 0.5
    elif state.macd < state.macd_signal and state.macd <= 0:
        macd_score = -1.0
    else:
        macd_score = -0.45

    if state.rsi is None:
        rsi_score = None
    elif 50.0 <= state.rsi <= 68.0:
        rsi_score = 0.85
    elif 45.0 <= state.rsi < 50.0:
        rsi_score = 0.35
    elif 68.0 < state.rsi <= 75.0:
        rsi_score = 0.3
    elif state.rsi > 75.0:
        rsi_score = -0.75
    elif state.rsi < 30.0:
        rsi_score = 0.2 if previous and previous.rsi is not None and state.rsi > previous.rsi else -0.4
    elif previous and previous.rsi is not None and state.rsi > previous.rsi:
        rsi_score = 0.2
    else:
        rsi_score = -0.15

    if None in (state.tenkan, state.kijun, state.cloud_top, state.cloud_bottom):
        ichimoku_score = None
    elif state.close > state.cloud_top and state.tenkan >= state.kijun:
        ichimoku_score = 1.0
    elif state.close > state.cloud_top:
        ichimoku_score = 0.65
    elif state.close >= state.cloud_bottom and state.tenkan >= state.kijun:
        ichimoku_score = 0.25
    elif state.close < state.cloud_bottom and state.tenkan < state.kijun:
        ichimoku_score = -1.0
    elif state.close < state.cloud_bottom:
        ichimoku_score = -0.65
    else:
        ichimoku_score = -0.2

    return {
        "ichimoku": ichimoku_score,
        "macd": macd_score,
        "rsi": rsi_score,
        "ema": ema_score,
        "sma": sma_score,
    }


def _component_key(timeframe: str, indicator: str) -> str:
    return f"{timeframe}.{indicator}"


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    sanitized = {
        key: _clamp(float(value) if math.isfinite(float(value)) else 0.0, 0.002, 0.35)
        for key, value in weights.items()
    }
    total = sum(sanitized.values())
    if total <= 0:
        return {key: 1.0 / max(1, len(sanitized)) for key in sanitized}
    return {key: value / total for key, value in sanitized.items()}


def _initial_weights(config: EntryConfig) -> dict[str, float]:
    indicator_bias = {name: 1.0 for name in INDICATORS}
    timeframe_bias = {"daily": 1.25, "weekly": 1.05, "monthly": 0.9, "yearly": 0.65}
    if config.mode in {"trend", "breakout", "conservative"}:
        indicator_bias.update({"ichimoku": 1.35, "macd": 1.2, "ema": 1.2, "sma": 1.2, "rsi": 0.75})
    if config.mode == "pullback":
        indicator_bias.update({"rsi": 1.55, "ichimoku": 1.25, "macd": 1.05, "ema": 0.85, "sma": 0.85})
    if config.mode == "breakout":
        timeframe_bias["daily"] = 1.5
        timeframe_bias["weekly"] = 1.15
    return _normalize_weights({
        _component_key(timeframe, indicator): timeframe_bias[timeframe] * indicator_bias[indicator]
        for timeframe in TIMEFRAMES
        for indicator in INDICATORS
    })


def _signal_at(
    context: dict[str, TimeframeData],
    daily_index: int,
    weights: dict[str, float],
) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    timeframes: dict[str, dict[str, Any]] = {}
    for timeframe, series in context.items():
        state_index = series.completed_index_by_daily_bar[daily_index]
        if state_index is None or state_index < 0 or state_index >= len(series.states):
            timeframes[timeframe] = {"status": "WAITING_FOR_COMPLETED_BUCKET"}
            continue
        state = series.states[state_index]
        previous = series.states[state_index - 1] if state_index else None
        scores = _component_scores(state, previous)
        available: dict[str, float] = {}
        for indicator, score in scores.items():
            if score is None:
                continue
            key = _component_key(timeframe, indicator)
            available[key] = float(score)
            components[key] = {
                "timeframe": timeframe,
                "indicator": indicator,
                "score": _round(score),
                "base_weight": _round(weights.get(key, 0.0), 8),
            }
        local_denominator = sum(weights.get(key, 0.0) for key in available)
        local_score = (
            sum(weights.get(key, 0.0) * score for key, score in available.items()) / local_denominator
            if local_denominator > 0 else None
        )
        timeframes[timeframe] = {
            "status": "READY" if available else "INDICATOR_WARMUP",
            "as_of": state.date,
            "score": _round(local_score),
            "values": _state_values(state),
            "available_components": sorted(key.split(".", 1)[1] for key in available),
        }

    denominator = sum(weights.get(key, 0.0) for key in components)
    score = (
        sum(weights.get(key, 0.0) * float(item["score"]) for key, item in components.items()) / denominator
        if denominator > 0 else 0.0
    )
    effective_weights = {
        key: weights.get(key, 0.0) / denominator
        for key in components
    } if denominator > 0 else {}
    for key, item in components.items():
        item["effective_weight"] = _round(effective_weights.get(key, 0.0), 8)
        item["contribution"] = _round(effective_weights.get(key, 0.0) * float(item["score"]), 8)
    positive = sorted(
        (dict(item, key=key) for key, item in components.items() if float(item["score"]) >= 0.2),
        key=lambda item: float(item["contribution"]),
        reverse=True,
    )
    negative = sorted(
        (dict(item, key=key) for key, item in components.items() if float(item["score"]) <= -0.2),
        key=lambda item: float(item["contribution"]),
    )
    daily_values = timeframes.get("daily", {}).get("values") or {}
    return {
        "date": context["daily"].states[daily_index].date,
        "score": _round(score, 8),
        "components": components,
        "effective_weights": {key: _round(value, 8) for key, value in effective_weights.items()},
        "timeframes": timeframes,
        "positive_components": positive,
        "negative_components": negative,
        "positive_count": len(positive),
        "negative_count": len(negative),
        "daily_rsi": daily_values.get("rsi"),
        "daily_breakout": bool(daily_values.get("breakout_up")),
    }


def _entry_gate(signal: dict[str, Any], config: EntryConfig) -> tuple[bool, str]:
    if not signal["components"]:
        return False, "indicator_warmup"
    if float(signal["score"]) < config.threshold:
        return False, "score_below_threshold"
    if int(signal["positive_count"]) < config.min_positive_components:
        return False, "not_enough_confirmations"
    if int(signal["negative_count"]) >= max(3, int(signal["positive_count"])):
        return False, "indicator_conflict"

    daily_score = signal["timeframes"].get("daily", {}).get("score")
    weekly_score = signal["timeframes"].get("weekly", {}).get("score")
    monthly_score = signal["timeframes"].get("monthly", {}).get("score")
    if config.mode == "conservative":
        if daily_score is None or daily_score < 0.15:
            return False, "daily_confirmation_missing"
        if weekly_score is None or weekly_score < 0:
            return False, "weekly_confirmation_missing"
        if monthly_score is None or monthly_score < -0.1:
            return False, "monthly_trend_not_supportive"
    elif config.mode == "trend":
        if daily_score is None or daily_score < 0.1:
            return False, "daily_trend_missing"
        if weekly_score is None or weekly_score < 0:
            return False, "weekly_trend_missing"
    elif config.mode == "breakout":
        if not signal["daily_breakout"]:
            return False, "daily_breakout_missing"
        if weekly_score is not None and weekly_score < -0.1:
            return False, "weekly_trend_opposes_breakout"
    elif config.mode == "pullback":
        rsi = signal.get("daily_rsi")
        if rsi is None or not 35.0 <= float(rsi) <= 60.0:
            return False, "pullback_rsi_outside_zone"
        if weekly_score is None or weekly_score < 0.05:
            return False, "higher_timeframe_not_bullish"
    return True, f"{config.mode}_multi_timeframe_entry"


def _describe_components(items: Sequence[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "component": item["key"],
            "score": item["score"],
            "effective_weight": item.get("effective_weight"),
            "contribution": item.get("contribution"),
        }
        for item in items[:limit]
    ]


def _open_trade(
    bars: Sequence[Bar],
    daily_states: Sequence[IndicatorState],
    decision_index: int,
    signal: dict[str, Any],
    config: EntryConfig,
) -> dict[str, Any]:
    entry_index = decision_index + 1
    entry_price = bars[entry_index].open if bars[entry_index].open > 0 else bars[entry_index].close
    decision_price = bars[decision_index].close
    atr = daily_states[decision_index].atr
    atr_ratio = atr / decision_price if atr and decision_price > 0 else 0.02
    stop_pct = _clamp(config.stop_atr * atr_ratio, 0.01, 0.18)
    target_pct = _clamp(config.target_atr * atr_ratio, 0.012, 0.35)
    return {
        "direction": "LONG",
        "decision_index": decision_index,
        "decision_date": bars[decision_index].date,
        "entry_index": entry_index,
        "entry_date": bars[entry_index].date,
        "entry_price": _round(entry_price),
        "planned_exit_index": min(len(bars) - 1, entry_index + max(1, config.holding_bars) - 1),
        "stop_price": _round(entry_price * (1.0 - stop_pct)),
        "target_price": _round(entry_price * (1.0 + target_pct)),
        "entry_score": signal["score"],
        "entry_reason": config.mode + "_multi_timeframe_entry",
        "positive_indicators": _describe_components(signal["positive_components"]),
        "conflicting_indicators": _describe_components(signal["negative_components"]),
        "component_scores": {
            key: item["score"] for key, item in signal["components"].items()
        },
        "weights_before": signal["effective_weights"],
    }


def _settle_trade(
    active: dict[str, Any],
    bars: Sequence[Bar],
    index: int,
    transaction_cost: float,
) -> dict[str, Any] | None:
    if index < int(active["entry_index"]):
        return None
    bar = bars[index]
    stop = float(active["stop_price"])
    target = float(active["target_price"])
    hit_stop = bar.low <= stop
    hit_target = bar.high >= target
    if hit_stop and hit_target:
        # Daily OHLC cannot prove intraday order, so use the loss side.  This
        # avoids optimistic target-first backtesting.
        exit_price, exit_reason = stop, "ambiguous_bar_stop_first"
    elif hit_stop:
        exit_price, exit_reason = stop, "stop_loss"
    elif hit_target:
        exit_price, exit_reason = target, "take_profit"
    elif index >= int(active["planned_exit_index"]):
        exit_price, exit_reason = bar.close, "time_exit"
    else:
        return None
    entry = float(active["entry_price"])
    gross_return = exit_price / entry - 1.0 if entry > 0 else 0.0
    net_return = gross_return - transaction_cost
    trade = dict(active)
    trade.update(
        {
            "exit_index": index,
            "exit_date": bar.date,
            "exit_price": _round(exit_price),
            "exit_reason": exit_reason,
            "gross_return_pct": _round(gross_return * 100.0, 6),
            "net_return_pct": _round(net_return * 100.0, 6),
            "outcome": "WIN" if net_return > 0 else "LOSS" if net_return < 0 else "FLAT",
        }
    )
    conflicts = trade.get("conflicting_indicators") or []
    if net_return > 0:
        trade["success_reason"] = (
            "target_reached_with_multi_timeframe_agreement"
            if exit_reason == "take_profit"
            else "positive_return_after_multi_timeframe_entry"
        )
        trade["failure_reason"] = None
    elif exit_reason in {"stop_loss", "ambiguous_bar_stop_first"}:
        trade["success_reason"] = None
        trade["failure_reason"] = "stop_loss_or_intraday_ambiguity"
    elif conflicts:
        trade["success_reason"] = None
        trade["failure_reason"] = "indicator_conflict_not_filtered"
    else:
        trade["success_reason"] = None
        trade["failure_reason"] = "time_exit_loss_or_false_entry"
    return trade


def _update_weights(
    weights: dict[str, float],
    trade: dict[str, Any],
    *,
    learning_rate: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Update only after a trade outcome is known, using multiplicative weights."""

    before = dict(weights)
    realized = float(trade.get("net_return_pct") or 0.0) / 100.0
    reward = _clamp(realized / 0.035, -1.0, 1.0)
    for key, raw_score in (trade.get("component_scores") or {}).items():
        if key not in weights:
            continue
        try:
            score = _clamp(float(raw_score), -1.0, 1.0)
        except (TypeError, ValueError):
            continue
        weights[key] = _clamp(weights[key] * math.exp(learning_rate * reward * score), 0.002, 0.35)
    after = _normalize_weights(weights)
    changed = sorted(
        (
            {
                "component": key,
                "before": _round(before[key], 8),
                "after": _round(after[key], 8),
                "delta": _round(after[key] - before[key], 8),
            }
            for key in after
        ),
        key=lambda item: abs(float(item["delta"])),
        reverse=True,
    )
    return after, {
        "after_trade": trade["decision_date"],
        "outcome": trade["outcome"],
        "realized_return_pct": trade["net_return_pct"],
        "top_weight_changes": changed[:6],
    }


def _trade_metrics(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    returns = [float(item["net_return_pct"]) / 100.0 for item in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    equity, peak, maximum_drawdown = 1.0, 1.0, 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak:
            maximum_drawdown = min(maximum_drawdown, equity / peak - 1.0)
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (None if not wins else float("inf"))
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "flats": len(returns) - len(wins) - len(losses),
        "win_rate_pct": _round(len(wins) / len(returns) * 100.0, 4) if returns else None,
        "mean_net_return_pct": _round(mean(returns) * 100.0, 6) if returns else None,
        "cumulative_return_pct": _round((equity - 1.0) * 100.0, 6),
        "max_drawdown_pct": _round(maximum_drawdown * 100.0, 6),
        "profit_factor": _round(profit_factor, 6) if profit_factor is not None and math.isfinite(profit_factor) else ("infinite" if profit_factor else None),
        "expectancy_pct": _round(mean(returns) * 100.0, 6) if returns else None,
    }


def _trades_in_range(trades: Sequence[dict[str, Any]], start: int, stop: int) -> list[dict[str, Any]]:
    return [
        item for item in trades
        if start <= int(item.get("decision_index", -1)) < stop
    ]


def _range_boundaries(bar_count: int, initial_history: int) -> dict[str, int]:
    start = max(10, min(int(initial_history), max(10, bar_count - 1)))
    decisions = max(0, bar_count - start - 1)
    train_end = min(bar_count - 1, start + max(1, int(decisions * 0.60)))
    validation_end = min(bar_count - 1, train_end + max(1, int(decisions * 0.20)))
    return {"start": start, "train_end": train_end, "validation_end": validation_end, "end": bar_count - 1}


def _candidate_score(metrics: dict[str, Any]) -> float:
    """Rank validation candidates without looking at frozen test results.

    This score only resolves the order among candidates. A separate fixed gate
    below decides whether the validation evidence is sufficient at all.
    """

    trades = int(metrics.get("trades") or 0)
    if trades < MIN_VALIDATION_TRADES:
        # Do not let one or two lucky entries outrank an evidence-backed model.
        return -100000.0 + trades
    cumulative = float(metrics.get("cumulative_return_pct") or 0.0)
    drawdown = abs(float(metrics.get("max_drawdown_pct") or 0.0))
    win_rate = float(metrics.get("win_rate_pct") or 0.0)
    factor_value = metrics.get("profit_factor")
    factor = 0.0 if factor_value in (None, "infinite") else min(3.0, float(factor_value))
    return cumulative - 0.75 * drawdown + 0.04 * win_rate + 1.5 * factor


def _robustness_gate(
    metrics: dict[str, Any],
    *,
    phase: str,
    minimum_trades: int,
) -> dict[str, Any]:
    """Return fixed, auditable after-cost quality checks for one data range."""

    trades = int(metrics.get("trades") or 0)
    cumulative_return = float(metrics.get("cumulative_return_pct") or 0.0)
    max_drawdown = float(metrics.get("max_drawdown_pct") or 0.0)
    raw_factor = metrics.get("profit_factor")
    profit_factor_ok = raw_factor == "infinite" or (
        isinstance(raw_factor, (int, float))
        and math.isfinite(float(raw_factor))
        and float(raw_factor) > MIN_PROFIT_FACTOR
    )
    checks = {
        "minimum_trade_count": trades >= minimum_trades,
        "positive_cumulative_return_after_costs": cumulative_return > 0.0,
        "profit_factor_above_one": profit_factor_ok,
        "controlled_max_drawdown": max_drawdown >= MAX_ACCEPTABLE_DRAWDOWN_PCT,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "phase": phase,
        "passed": not failed_checks,
        "thresholds": {
            "minimum_trades": minimum_trades,
            "minimum_profit_factor_exclusive": MIN_PROFIT_FACTOR,
            "minimum_cumulative_return_pct_exclusive": 0.0,
            "maximum_drawdown_pct": MAX_ACCEPTABLE_DRAWDOWN_PCT,
        },
        "observed": {
            "trades": trades,
            "cumulative_return_pct": _round(cumulative_return, 6),
            "profit_factor": raw_factor,
            "max_drawdown_pct": _round(max_drawdown, 6),
        },
        "checks": checks,
        "failed_checks": failed_checks,
    }


def _configs() -> tuple[EntryConfig, ...]:
    """Bounded improvement search; round 2 is stricter after baseline errors."""

    return (
        EntryConfig("balanced-r1-05", "متعادل کوتاه", "balanced", 0.30, 5, 1.20, 1.80, 0.20, 2, 1, "Baseline adaptive five-bar entry."),
        EntryConfig("balanced-r1-10", "متعادل", "balanced", 0.36, 10, 1.45, 2.30, 0.24, 3, 1, "Balanced multi-indicator entry."),
        EntryConfig("trend-r1-10", "روند", "trend", 0.38, 10, 1.50, 2.50, 0.24, 3, 1, "Daily and weekly trend confirmation."),
        EntryConfig("conservative-r1-15", "محافظه‌کار", "conservative", 0.50, 15, 1.35, 2.80, 0.18, 4, 1, "Requires daily, weekly and monthly support."),
        EntryConfig("breakout-r1-10", "شکست", "breakout", 0.32, 10, 1.35, 2.40, 0.23, 3, 1, "Daily breakout with adaptive confirmation."),
        EntryConfig("pullback-r1-10", "پولبک", "pullback", 0.28, 10, 1.25, 2.10, 0.22, 3, 1, "Trend-supported RSI pullback entry."),
        EntryConfig("balanced-r2-12", "متعادل پالایش‌شده", "balanced", 0.43, 12, 1.35, 2.60, 0.16, 4, 2, "Stricter confirmation after noisy baseline entries."),
        EntryConfig("trend-r2-15", "روند پالایش‌شده", "trend", 0.48, 15, 1.45, 3.00, 0.16, 4, 2, "Stricter trend consistency and slower learning."),
        EntryConfig("conservative-r2-20", "محافظه‌کار پالایش‌شده", "conservative", 0.58, 20, 1.25, 3.10, 0.14, 4, 2, "Lower turnover and multi-timeframe gate."),
        EntryConfig("breakout-r2-15", "شکست پالایش‌شده", "breakout", 0.44, 15, 1.30, 2.80, 0.17, 4, 2, "Filters weak breakouts with stronger score."),
        EntryConfig("pullback-r2-15", "پولبک پالایش‌شده", "pullback", 0.36, 15, 1.20, 2.65, 0.16, 4, 2, "Filters RSI pullbacks without higher-trend support."),
        EntryConfig("stability-r2-20", "پایداری", "conservative", 0.62, 20, 1.10, 2.90, 0.12, 5, 2, "Low-turnover stability candidate."),
    )


def _simulate(
    bars: Sequence[Bar],
    context: dict[str, TimeframeData],
    config: EntryConfig,
    *,
    initial_history: int,
    transaction_cost_pct: float,
) -> dict[str, Any]:
    weights = _initial_weights(config)
    initial_weights = dict(weights)
    start = max(10, min(int(initial_history), max(10, len(bars) - 1)))
    trades: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    active: dict[str, Any] | None = None
    latest_signal: dict[str, Any] | None = None
    latest_eligible = False
    latest_reason = "indicator_warmup"

    for index in range(start, len(bars)):
        if active is not None:
            settled = _settle_trade(active, bars, index, transaction_cost_pct / 100.0)
            if settled is None:
                rejections["position_already_open"] += 1
                continue
            trades.append(settled)
            weights, update = _update_weights(weights, settled, learning_rate=config.learning_rate)
            updates.append(update)
            active = None

        signal = _signal_at(context, index, weights)
        eligible, reason = _entry_gate(signal, config)
        if index == len(bars) - 1:
            latest_signal = signal
            latest_eligible, latest_reason = eligible, reason
            if not eligible:
                rejections[reason] += 1
            break
        if not eligible:
            rejections[reason] += 1
            continue
        active = _open_trade(context["daily"].bars, context["daily"].states, index, signal, config)

    if latest_signal is None and bars:
        latest_signal = _signal_at(context, len(bars) - 1, weights)
        latest_eligible, latest_reason = _entry_gate(latest_signal, config)
    return {
        "config": config,
        "trades": trades,
        "initial_weights": initial_weights,
        "weight_updates": updates,
        "final_weights": weights,
        "rejections": dict(rejections),
        "open_position": active,
        "latest_signal": latest_signal,
        "latest_eligible": latest_eligible,
        "latest_reason": latest_reason,
        "start_index": start,
    }


def _diagnostics(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    losses = [item for item in trades if item.get("outcome") == "LOSS"]
    wins = [item for item in trades if item.get("outcome") == "WIN"]
    failure_reasons = Counter(str(item.get("failure_reason") or "unspecified") for item in losses)
    success_reasons = Counter(str(item.get("success_reason") or "unspecified") for item in wins)
    conflicts = Counter(
        detail.get("component", "unknown")
        for item in losses
        for detail in (item.get("conflicting_indicators") or [])
        if isinstance(detail, dict)
    )
    positives = Counter(
        detail.get("component", "unknown")
        for item in wins
        for detail in (item.get("positive_indicators") or [])
        if isinstance(detail, dict)
    )
    return {
        "losses_by_reason": dict(failure_reasons),
        "successes_by_reason": dict(success_reasons),
        "conflicting_components_on_losses": dict(conflicts.most_common(10)),
        "supporting_components_on_wins": dict(positives.most_common(10)),
        "loss_examples": losses[-10:],
        "win_examples": wins[-10:],
    }


def _weight_tree(weights: dict[str, float]) -> dict[str, dict[str, float]]:
    return {
        timeframe: {
            indicator: _round(weights.get(_component_key(timeframe, indicator), 0.0), 8) or 0.0
            for indicator in INDICATORS
        }
        for timeframe in TIMEFRAMES
    }


def _segments(
    bars: Sequence[Bar],
    trades: Sequence[dict[str, Any]],
    *,
    phase_ranges: Sequence[tuple[str, int, int]],
    evaluation_window: int,
) -> list[dict[str, Any]]:
    """Split every chronological phase into fixed-size, auditable windows."""

    result: list[dict[str, Any]] = []
    number = 1
    for phase, start, stop in phase_ranges:
        phase_number = 1
        for left in range(start, stop, max(1, evaluation_window)):
            right = min(stop, left + max(1, evaluation_window))
            if right <= left:
                continue
            outcomes_closed = sum(
                1
                for trade in trades
                if left <= int(trade.get("exit_index", -1)) < right
            )
            result.append(
                {
                    "segment": number,
                    "phase": phase,
                    "phase_segment": phase_number,
                    "from": bars[left].date,
                    "to": bars[right - 1].date,
                    "decision_days": right - left,
                    "history_available_bars": left,
                    "known_through": bars[left - 1].date if left > 0 else None,
                    "is_frozen_test": phase == "test",
                    "entries": len(_trades_in_range(trades, left, right)),
                    "outcomes_closed_for_weight_learning": outcomes_closed,
                    "metrics": _trade_metrics(_trades_in_range(trades, left, right)),
                }
            )
            number += 1
            phase_number += 1
    return result


def _compact_current(
    simulation: dict[str, Any],
    bars: Sequence[Bar],
) -> dict[str, Any]:
    signal = simulation.get("latest_signal") or {}
    if simulation.get("open_position"):
        status = "POSITION_OPEN"
        reason = "A previous long-only simulated entry is still open."
    elif simulation.get("latest_eligible"):
        status = "ENTRY_CANDIDATE"
        reason = simulation.get("latest_reason")
    else:
        status = "WAIT"
        reason = simulation.get("latest_reason")
    return {
        "as_of": bars[-1].date if bars else None,
        "status": status,
        "long_only": True,
        "reason": reason,
        "composite_score": signal.get("score"),
        "positive_indicators": _describe_components(signal.get("positive_components") or []),
        "conflicting_indicators": _describe_components(signal.get("negative_components") or []),
        "timeframes": signal.get("timeframes") or {},
        "open_position": simulation.get("open_position"),
    }


def _apply_evidence_to_current_entry(
    current_entry: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, Any]:
    """Keep an unvalidated technical signal from looking like an entry order."""

    current = dict(current_entry)
    paper_eligible = promotion.get("decision") == "PAPER_WATCH_CANDIDATE"
    current["paper_monitoring_eligible"] = paper_eligible
    if not paper_eligible and current.get("status") == "ENTRY_CANDIDATE":
        current["technical_signal_status"] = "ENTRY_CANDIDATE"
        current["technical_reason"] = current.get("reason")
        current["status"] = "RESEARCH_SIGNAL_ONLY"
        current["reason"] = "insufficient_validation_or_test_evidence"
    return current


def _promotion(selected: dict[str, Any]) -> dict[str, Any]:
    """Permit paper monitoring only when validation and test pass fixed gates."""

    metrics = selected.get("range_metrics") or {}
    validation_gate = selected.get("validation_gate") or _robustness_gate(
        metrics.get("validation") or {},
        phase="validation",
        minimum_trades=MIN_VALIDATION_TRADES,
    )
    test_gate = selected.get("test_gate") or _robustness_gate(
        metrics.get("test") or {},
        phase="test",
        minimum_trades=MIN_TEST_TRADES,
    )
    if validation_gate["passed"] and test_gate["passed"]:
        return {
            "decision": "PAPER_WATCH_CANDIDATE",
            "reason": "Validation-selected candidate remained positive on the untouched test range; paper monitoring is still required.",
            "validation_gate": validation_gate,
            "test_gate": test_gate,
        }
    failed = []
    if not validation_gate["passed"]:
        failed.append("validation: " + ", ".join(validation_gate["failed_checks"]))
    if not test_gate["passed"]:
        failed.append("test: " + ", ".join(test_gate["failed_checks"]))
    return {
        "decision": "RESEARCH_ONLY",
        "reason": (
            "The candidate lacks sufficient after-cost evidence in a required chronological range "
            f"({'; '.join(failed)}); do not treat it as a trading instruction."
        ),
        "validation_gate": validation_gate,
        "test_gate": test_gate,
    }


def _persist(profile: dict[str, Any], root: str | Path) -> dict[str, Any]:
    symbol = str(profile.get("symbol") or "UNKNOWN")
    directory = Path(root) / safe_symbol(symbol) / "symbol_profiles"
    directory.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    artifact = directory / f"{run_id}.json"
    latest = directory / "latest.json"
    profile["artifact_path"] = str(artifact)
    profile["latest_artifact_path"] = str(latest)
    encoded = json.dumps(profile, ensure_ascii=False, indent=2)
    artifact.write_text(encoded, encoding="utf-8")
    latest.write_text(encoded, encoding="utf-8")
    return profile


def load_latest_symbol_profile(symbol: str, root: str | Path = "runtime/learning") -> dict[str, Any] | None:
    path = Path(root) / safe_symbol(symbol) / "symbol_profiles" / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def summarize_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a small dashboard/ChatGPT-safe view without the full trade trace."""

    if not isinstance(profile, dict):
        return None
    selected = profile.get("selected_model") or {}
    return {
        "status": profile.get("status"),
        "engine_version": profile.get("engine_version"),
        "symbol": profile.get("symbol"),
        "coverage": profile.get("coverage"),
        "protocol": profile.get("protocol"),
        "selected_model": {
            "config": selected.get("config"),
            "validation_metrics": (selected.get("range_metrics") or {}).get("validation"),
            "test_metrics": (selected.get("range_metrics") or {}).get("test"),
            "selection_score": selected.get("selection_score"),
            "selection_status": selected.get("selection_status"),
            "validation_gate": selected.get("validation_gate"),
            "test_gate": selected.get("test_gate"),
        },
        "current_entry": profile.get("current_entry"),
        "indicator_weights": profile.get("indicator_weights"),
        "promotion": profile.get("promotion"),
        "walk_forward": profile.get("walk_forward"),
        "failure_diagnostics": {
            key: value
            for key, value in (profile.get("failure_diagnostics") or {}).items()
            if key not in {"loss_examples", "win_examples"}
        },
        "artifact_path": profile.get("artifact_path"),
    }


def walk_forward_entry_simulation(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str = "",
    config_id: str = "balanced-r1-10",
    initial_history: int = 20,
    transaction_cost_pct: float = 0.35,
    max_bars: int | None = None,
) -> dict[str, Any]:
    """Run one long-only configuration for tests and audit tooling.

    ``max_bars`` deliberately truncates before feature construction, making it
    possible to demonstrate that later rows cannot alter earlier decisions.
    """

    bars = normalize_bars(rows)
    if max_bars is not None:
        bars = bars[: max(0, int(max_bars))]
    config = next((item for item in _configs() if item.config_id == config_id), None)
    if config is None:
        raise ValueError(f"Unknown entry config: {config_id}")
    if len(bars) < max(12, initial_history + 2):
        return {"status": "INSUFFICIENT_HISTORY", "symbol": symbol, "bars": len(bars)}
    simulation = _simulate(
        bars,
        _build_context(bars),
        config,
        initial_history=initial_history,
        transaction_cost_pct=transaction_cost_pct,
    )
    return {
        "status": "COMPLETE",
        "symbol": symbol,
        "config": asdict(config),
        "long_only": True,
        "no_lookahead": True,
        "trades": simulation["trades"],
        "metrics": _trade_metrics(simulation["trades"]),
        "final_weights": _weight_tree(simulation["final_weights"]),
        "latest": _compact_current(simulation, bars),
    }


def build_symbol_profile(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str,
    years: int = 10,
    initial_history: int = 20,
    evaluation_window: int = 30,
    transaction_cost_pct: float = 0.35,
    output_root: str | Path = "runtime/learning",
    persist: bool = True,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Train/evaluate one independent adaptive entry model for one symbol."""

    all_bars = normalize_bars(rows)
    bars = _limit_to_years(all_bars, max(1, int(years)))
    if len(bars) < max(12, int(initial_history) + 2):
        result = {
            "schema_version": "1.1",
            "engine_version": ENGINE_VERSION,
            "status": "INSUFFICIENT_HISTORY",
            "symbol": symbol,
            "source_metadata": dict(source_metadata or {}),
            "bars": len(bars),
            "required_bars": max(12, int(initial_history) + 2),
            "long_only": True,
            "no_lookahead": True,
        }
        return _persist(result, output_root) if persist else result

    context = _build_context(bars)
    bounds = _range_boundaries(len(bars), initial_history)
    simulations = [
        _simulate(
            bars,
            context,
            config,
            initial_history=initial_history,
            transaction_cost_pct=transaction_cost_pct,
        )
        for config in _configs()
    ]
    reports: list[dict[str, Any]] = []
    for simulation in simulations:
        trades = simulation["trades"]
        range_metrics = {
            "train": _trade_metrics(_trades_in_range(trades, bounds["start"], bounds["train_end"])),
            "validation": _trade_metrics(_trades_in_range(trades, bounds["train_end"], bounds["validation_end"])),
            "test": _trade_metrics(_trades_in_range(trades, bounds["validation_end"], bounds["end"])),
            "all": _trade_metrics(trades),
        }
        validation_gate = _robustness_gate(
            range_metrics["validation"],
            phase="validation",
            minimum_trades=MIN_VALIDATION_TRADES,
        )
        test_gate = _robustness_gate(
            range_metrics["test"],
            phase="test",
            minimum_trades=MIN_TEST_TRADES,
        )
        reports.append(
            {
                "simulation": simulation,
                "config": asdict(simulation["config"]),
                "range_metrics": range_metrics,
                "selection_score": _round(_candidate_score(range_metrics["validation"]), 8),
                "validation_gate": validation_gate,
                "test_gate": test_gate,
                "selection_eligible": validation_gate["passed"],
            }
        )
    reports.sort(
        key=lambda item: (
            bool(item["selection_eligible"]),
            float(item["selection_score"]),
            int(item["range_metrics"]["validation"].get("trades") or 0),
        ),
        reverse=True,
    )
    selected = reports[0]
    selection_status = (
        "VALIDATION_QUALIFIED"
        if selected["selection_eligible"]
        else "INSUFFICIENT_VALIDATION_EVIDENCE"
    )
    selection_rule = (
        "highest validation robustness score among candidates passing all fixed validation gates; "
        "frozen test excluded from selection"
        if selected["selection_eligible"]
        else "no candidate passed the fixed validation gates; highest-ranked validation-only "
        "diagnostic fallback is shown for research, not promotion"
    )
    selected_simulation = selected["simulation"]
    selected_trades = selected_simulation["trades"]
    diagnostics = _diagnostics(selected_trades)
    phase_ranges = (
        ("train", bounds["start"], bounds["train_end"]),
        ("validation", bounds["train_end"], bounds["validation_end"]),
        ("test", bounds["validation_end"], bounds["end"]),
    )
    walk_forward_segments = _segments(
        bars,
        selected_trades,
        phase_ranges=phase_ranges,
        evaluation_window=evaluation_window,
    )
    promotion = _promotion(selected)
    current_entry = _apply_evidence_to_current_entry(
        _compact_current(selected_simulation, bars),
        promotion,
    )
    bootstrap_history = {
        "from": bars[0].date,
        "to": bars[bounds["start"] - 1].date if bounds["start"] > 0 else bars[0].date,
        "bars": bounds["start"],
        "purpose": "Initial history is visible before the first end-of-day decision; no trade is evaluated in this bootstrap period.",
    }
    profile = {
        "schema_version": "1.1",
        "engine_version": ENGINE_VERSION,
        "status": "COMPLETE",
        "symbol": symbol,
        "source_metadata": dict(source_metadata or {}),
        "coverage": {
            "requested_years": int(years),
            "available_bars_before_cap": len(all_bars),
            "bars_used": len(bars),
            "first_date": bars[0].date,
            "last_date": bars[-1].date,
            "timeframes": list(TIMEFRAMES),
        },
        "protocol": {
            "long_only_entries": True,
            "decision_time": "end_of_day",
            "entry_time": "next_open",
            "transaction_cost_pct_round_trip": transaction_cost_pct,
            "higher_timeframes_use_previous_completed_bucket": True,
            "ichimoku_cloud_uses_lagged_projected_spans": True,
            "weights_update_only_after_realized_trade": True,
            "candidate_selection": "validation_only",
            "frozen_test_used_for_candidate_selection": False,
            "no_lookahead": True,
            "initial_history_bars": int(initial_history),
            "evaluation_window_bars": int(evaluation_window),
        },
        "indicator_specification": {
            "indicators": list(INDICATORS),
            "parameters_by_timeframe": _PARAMETERS,
            "annual_periods_are_scaled": True,
        },
        "ranges": {
            name: {
                "from": bars[left].date,
                "to": bars[right - 1].date if right > left else bars[left].date,
                "start_index": left,
                "stop_index": right,
            }
            for name, left, right in (
                ("bootstrap", 0, bounds["start"]),
                ("train", bounds["start"], bounds["train_end"]),
                ("validation", bounds["train_end"], bounds["validation_end"]),
                ("test", bounds["validation_end"], bounds["end"]),
            )
        },
        "candidate_reports": [
            {
                "config": item["config"],
                "range_metrics": item["range_metrics"],
                "selection_score": item["selection_score"],
                "selection_eligible": item["selection_eligible"],
                "validation_gate": item["validation_gate"],
                "test_gate": item["test_gate"],
            }
            for item in reports
        ],
        "selected_model": {
            "config": selected["config"],
            "range_metrics": selected["range_metrics"],
            "selection_score": selected["selection_score"],
            "selection_status": selection_status,
            "validation_gate": selected["validation_gate"],
            "test_gate": selected["test_gate"],
            "selection_rule": selection_rule,
        },
        "initial_indicator_weights": _weight_tree(selected_simulation["initial_weights"]),
        "indicator_weights": _weight_tree(selected_simulation["final_weights"]),
        "current_entry": current_entry,
        "analysis_path": {
            "entries_and_outcomes": selected_trades,
            "weight_updates": selected_simulation["weight_updates"],
            "rejected_entry_reasons": selected_simulation["rejections"],
            "open_position": selected_simulation["open_position"],
        },
        "failure_diagnostics": diagnostics,
        "walk_forward": {
            "bootstrap_history": bootstrap_history,
            "segment_count": len(walk_forward_segments),
            "segments_cover": "Every decision day after bootstrap, split into chronological train, validation and frozen-test windows.",
            "test_policy": "Test segments never choose the configuration. They only simulate the already-selected online learner using outcomes available before each later decision.",
        },
        "walk_forward_segments": walk_forward_segments,
        "improvement_history": {
            "round_1_best_validation": next((
                {
                    "config": item["config"],
                    "selection_score": item["selection_score"],
                    "validation_metrics": item["range_metrics"]["validation"],
                }
                for item in reports if item["config"]["improvement_round"] == 1
            ), None),
            "round_2_best_validation": next((
                {
                    "config": item["config"],
                    "selection_score": item["selection_score"],
                    "validation_metrics": item["range_metrics"]["validation"],
                }
                for item in reports if item["config"]["improvement_round"] == 2
            ), None),
            "rule": "Round 2 uses stricter candidate gates to address noisy/low-confirmation entries; both rounds are ranked only on validation.",
        },
        "ai_training": {
            "method": "online_multiplicative_indicator_weights",
            "per_symbol": True,
            "components": [f"{timeframe}.{indicator}" for timeframe in TIMEFRAMES for indicator in INDICATORS],
            "outcome_feedback": "trade close net return after costs",
            "weight_update_count": len(selected_simulation["weight_updates"]),
            "selection_evidence": "fixed after-cost validation gates before any paper-watch promotion",
        },
    }
    profile["promotion"] = promotion
    return _persist(profile, output_root) if persist else profile


__all__ = [
    "ENGINE_VERSION",
    "FOCUS_SYMBOLS",
    "INDICATORS",
    "TIMEFRAMES",
    "build_symbol_profile",
    "load_latest_symbol_profile",
    "normalize_bars",
    "summarize_profile",
    "walk_forward_entry_simulation",
]
