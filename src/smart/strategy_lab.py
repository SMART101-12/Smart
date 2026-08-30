"""Research strategy catalog and leakage-safe walk-forward examination.

The catalog contains 200 parameterized, deterministic strategy variants.  It
is a research ensemble: strategies are scored on observations whose outcomes
were already known at each simulated decision date.  No future indicator or
future return is supplied to the decision function.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence

import numpy as np

from .technical_analysis import Bar, Feature, build_features


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    family: str
    variant: int
    parameters: dict[str, float]
    description: str


def _family(
    family: str,
    label: str,
    description: str,
    params: Sequence[dict[str, float]],
) -> list[StrategySpec]:
    return [
        StrategySpec(
            strategy_id=f"{family}-{index + 1:02d}",
            name=f"{label} {index + 1:02d}",
            family=family,
            variant=index + 1,
            parameters=dict(item),
            description=description,
        )
        for index, item in enumerate(params)
    ]


@lru_cache(maxsize=1)
def strategy_catalog() -> tuple[StrategySpec, ...]:
    """Return exactly 200 reproducible strategy variants (20 x 10)."""

    periods = [(p, p * 4) for p in (3, 4, 5, 6, 8, 10, 12, 15, 20, 25)]
    rsi_bounds = [
        (25, 75), (28, 72), (30, 70), (32, 68), (35, 65),
        (20, 80), (22, 78), (27, 73), (33, 67), (38, 62),
    ]
    single_periods = [(p,) for p in (5, 8, 10, 12, 14, 20, 25, 30, 40, 50)]
    families: list[list[StrategySpec]] = [
        _family("sma_cross", "SMA crossover", "Fast/slow simple moving-average trend following.", [
            {"fast": a, "slow": b} for a, b in periods
        ]),
        _family("ema_cross", "EMA crossover", "Fast/slow exponential moving-average trend following.", [
            {"fast": a, "slow": b} for a, b in periods
        ]),
        _family("macd", "MACD regime", "MACD line versus signal line with zero-line confirmation.", [
            {"fast": a, "slow": b, "signal": 9} for a, b in periods
        ]),
        _family("rsi_reversion", "RSI mean reversion", "Oversold/overbought reversal with a neutral middle band.", [
            {"low": low, "high": high} for low, high in rsi_bounds
        ]),
        _family("rsi_momentum", "RSI momentum", "Momentum continuation above/below RSI thresholds.", [
            {"low": low, "high": high} for low, high in rsi_bounds
        ]),
        _family("bollinger_reversion", "Bollinger reversion", "Reversion from volatility-band extremes.", [
            {"period": p, "std": s} for (p,), s in zip(single_periods, (1.5, 1.8, 2.0, 2.2, 2.5, 1.2, 1.6, 2.4, 2.8, 3.0))
        ]),
        _family("bollinger_breakout", "Bollinger breakout", "Volatility expansion beyond the upper/lower band.", [
            {"period": p, "std": s} for (p,), s in zip(single_periods, (1.2, 1.5, 1.8, 2.0, 2.2, 2.5, 1.4, 2.4, 2.8, 3.0))
        ]),
        _family("donchian", "Donchian breakout", "Breakout of the prior rolling high/low channel.", [
            {"period": p} for (p,) in single_periods
        ]),
        _family("roc_momentum", "ROC momentum", "Rate-of-change continuation.", [
            {"period": p, "threshold": t} for (p,), t in zip(single_periods, (0.01, .015, .02, .025, .03, .04, .05, .06, .08, .10))
        ]),
        _family("volume_breakout", "Volume breakout", "Price direction confirmed by an abnormal volume ratio.", [
            {"ratio": r, "period": p} for (p,), r in zip(single_periods, (1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0))
        ]),
        _family("atr_trend", "ATR trend", "Directional move normalized by average true range.", [
            {"period": p, "multiple": m} for (p,), m in zip(single_periods, (0.3, .4, .5, .6, .7, .8, 1.0, 1.2, 1.5, 2.0))
        ]),
        _family("stochastic", "Stochastic oscillator", "Fast stochastic oversold/overbought reversal.", [
            {"period": p, "low": low, "high": high} for (p,), (low, high) in zip(single_periods, rsi_bounds)
        ]),
        _family("cci", "CCI trend/reversion", "Commodity-channel style deviation from a rolling typical-price mean.", [
            {"period": p, "threshold": t} for (p,), t in zip(single_periods, (50, 75, 100, 125, 150, 175, 200, 80, 120, 160))
        ]),
        _family("williams_r", "Williams %R", "Williams oscillator reversal at range extremes.", [
            {"period": p, "low": -90 + i * 2, "high": -10 - i * 2} for i, (p,) in enumerate(single_periods)
        ]),
        _family("obv_trend", "OBV trend", "On-balance-volume direction confirmed by price.", [
            {"period": p} for (p,) in single_periods
        ]),
        _family("vwap_reversion", "VWAP deviation", "Volume-weighted average price deviation reversion.", [
            {"period": p, "threshold": t} for (p,), t in zip(single_periods, (0.01, .015, .02, .025, .03, .04, .05, .06, .08, .10))
        ]),
        _family("triple_ma", "Triple moving average", "Fast/medium/slow alignment trend filter.", [
            {"fast": a, "medium": b, "slow": c} for a, b, c in (
                (3, 8, 20), (4, 10, 30), (5, 15, 40), (5, 20, 50), (8, 20, 50),
                (8, 20, 80), (10, 30, 100),
                (10, 40, 120), (12, 50, 150), (20, 50, 200),
            )
        ]),
        _family("support_resistance", "Support resistance", "Distance from prior rolling support/resistance.", [
            {"period": p, "buffer": b} for (p,), b in zip(single_periods, (.005, .008, .01, .012, .015, .02, .025, .03, .04, .05))
        ]),
        _family("price_action", "Price action", "Candle body and close-location continuation/reversal rules.", [
            {"body": b, "close_location": c} for b, c in zip((.1, .15, .2, .25, .3, .35, .4, .5, .6, .7), (.55, .58, .6, .62, .65, .68, .7, .72, .75, .8))
        ]),
        _family("multi_confirmation", "Multi confirmation", "Agreement of trend, momentum and volume signals.", [
            {"required": r, "period": p} for (p,), r in zip(single_periods, (1, 1, 2, 2, 2, 3, 3, 3, 3, 3))
        ]),
    ]
    result = tuple(item for group in families for item in group)
    if len(result) != 200:
        raise AssertionError(f"strategy catalog must contain 200 variants, got {len(result)}")
    return result


def strategy_definitions(strategy_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Return auditable definitions for all or a selected set of strategies."""
    wanted = set(strategy_ids or ())
    result = []
    for item in strategy_catalog():
        if wanted and item.strategy_id not in wanted:
            continue
        result.append({
            "id": item.strategy_id,
            "name": item.name,
            "family": item.family,
            "variant": item.variant,
            "parameters": item.parameters,
            "description": item.description,
        })
    return result


def _num(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, "", "-", "NA"):
            continue
        try:
            result = float(str(value).replace(",", ""))
            if math.isfinite(result):
                return result
        except (TypeError, ValueError):
            pass
    return 0.0


def bars_from_rows(rows: Iterable[dict[str, Any]]) -> list[Bar]:
    result: list[Bar] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = str(row.get("dEven") or row.get("source_date") or row.get("date") or "")
        date = date.replace("-", "").replace("/", "").strip()
        if len(date) != 8 or not date.isdigit():
            continue
        close = _num(row, "pClosing", "close", "pDrCotVal", "priceClosing")
        if close <= 0:
            continue
        result.append(Bar(
            date=date, close=close,
            high=_num(row, "pMax", "high", "pClosing") or close,
            low=_num(row, "pMin", "low", "pClosing") or close,
            open=_num(row, "pFirst", "open", "pClosing") or close,
            volume=_num(row, "qTotTran5J", "volume", "tvol"),
            value=_num(row, "qTotCap", "value"),
            trades=_num(row, "zTotTran", "trades"),
        ))
    return sorted({bar.date: bar for bar in result}.values(), key=lambda item: item.date)


class _IndicatorContext:
    """Cached rolling indicators shared by all 200 strategy variants."""

    def __init__(self, bars: Sequence[Bar], features: Sequence[Feature]) -> None:
        self.bars = bars
        self.features = features
        self.closes = np.asarray([bar.close for bar in bars], dtype=float)
        self.volumes = np.asarray([bar.volume for bar in bars], dtype=float)
        self._close_cumsum = np.concatenate(([0.0], np.cumsum(self.closes)))
        self._volume_cumsum = np.concatenate(([0.0], np.cumsum(self.volumes)))
        self._typical_volume_cumsum = np.concatenate(
            ([0.0], np.cumsum([
                ((bar.high + bar.low + bar.close) / 3) * bar.volume
                for bar in bars
            ]))
        )
        true_ranges = [
            max(bar.high - bar.low, 0.0)
            if i == 0
            else max(
                bar.high - bar.low,
                abs(bar.high - bars[i - 1].close),
                abs(bar.low - bars[i - 1].close),
            )
            for i, bar in enumerate(bars)
        ]
        self._tr_cumsum = np.concatenate(([0.0], np.cumsum(true_ranges)))
        obv_steps = [0.0]
        obv = 0.0
        for i in range(1, len(bars)):
            obv += (
                bars[i].volume if bars[i].close > bars[i - 1].close
                else -bars[i].volume if bars[i].close < bars[i - 1].close else 0.0
            )
            obv_steps.append(obv)
        self._obv = np.asarray(obv_steps, dtype=float)
        self._sma_cache: dict[int, list[float | None]] = {}
        self._ema_cache: dict[int, list[float | None]] = {}
        self._extra_cache: dict[tuple[int, int], dict[str, float]] = {}

    def sma(self, period: int, index: int) -> float | None:
        values = self._sma_cache.get(period)
        if values is None:
            values = [None] * len(self.closes)
            if len(self.closes) >= period:
                values = [
                    None if i + 1 < period else float(
                        (self._close_cumsum[i + 1] - self._close_cumsum[i + 1 - period]) / period
                    )
                    for i in range(len(self.closes))
                ]
            self._sma_cache[period] = values
        return values[index]

    def ema(self, period: int, index: int) -> float | None:
        values = self._ema_cache.get(period)
        if values is None:
            values = [None] * len(self.closes)
            if len(self.closes) >= period:
                value = float(np.mean(self.closes[:period]))
                values[period - 1] = value
                alpha = 2 / (period + 1)
                for i in range(period, len(self.closes)):
                    value = alpha * self.closes[i] + (1 - alpha) * value
                    values[i] = value
            self._ema_cache[period] = values
        return values[index]

    def extras(self, index: int, period: int = 20) -> dict[str, float]:
        key = (index, period)
        if key in self._extra_cache:
            return self._extra_cache[key]
        bars = self.bars
        closes = self.closes
        volumes = self.volumes
        start = max(0, index - period + 1)
        count = index - start + 1
        window_values = closes[start:index + 1]
        mean = float(np.mean(window_values))
        std = float(np.std(window_values))
        atr_start = max(0, index - 13)
        atr = float(
            (self._tr_cumsum[index + 1] - self._tr_cumsum[atr_start])
            / (index - atr_start + 1)
        )
        volume_total = float(self._volume_cumsum[index + 1] - self._volume_cumsum[start])
        vwap_den = volume_total
        vwap_num = float(
            self._typical_volume_cumsum[index + 1] - self._typical_volume_cumsum[start]
        )
        vwap = vwap_num / vwap_den if vwap_den else float(closes[index])
        prior = closes[max(0, index - 20):index]
        stochastic = (
            (closes[index] - float(np.min(prior))) / (float(np.max(prior)) - float(np.min(prior))) * 100
            if len(prior) and np.max(prior) != np.min(prior) else 50.0
        )
        obv = float(self._obv[index])
        bar = bars[index]
        result = {
            "sma": mean, "std": std, "upper": mean + 2 * std, "lower": mean - 2 * std,
            "atr": atr, "volume_ratio": closes[index] * 0 + (bar.volume / (volume_total / count) if volume_total else 0.0),
            "vwap": vwap, "stochastic": stochastic, "obv": obv,
            "body_pct": abs(bar.close - bar.open) / bar.close if bar.close else 0.0,
            "close_location": (bar.close - bar.low) / (bar.high - bar.low) if bar.high != bar.low else .5,
            "typical": (bar.high + bar.low + bar.close) / 3,
        }
        self._extra_cache[key] = result
        return result


def _signal(
    spec: StrategySpec,
    bars: Sequence[Bar],
    features: Sequence[Feature],
    index: int,
    context: _IndicatorContext | None = None,
) -> int:
    f = features[index]
    prev = features[index - 1] if index else None
    close = f.close
    ctx = context or _IndicatorContext(bars, features)
    period_hint = int(spec.parameters.get("period", spec.parameters.get("slow", 20)))
    x = ctx.extras(index, period_hint)
    p = spec.parameters
    family = spec.family
    if family in {"sma_cross", "ema_cross"}:
        fast, slow = int(p["fast"]), int(p["slow"])
        a = ctx.sma(fast, index) if family == "sma_cross" else ctx.ema(fast, index)
        b = ctx.sma(slow, index) if family == "sma_cross" else ctx.ema(slow, index)
        return 1 if a is not None and b is not None and a > b else -1 if a is not None and b is not None else 0
    if family == "macd":
        fast, slow = int(p["fast"]), int(p["slow"])
        a, b = ctx.ema(fast, index), ctx.ema(slow, index)
        return 1 if a is not None and b is not None and a > b and close > b else -1 if a is not None and b is not None and a < b and close < b else 0
    if family == "rsi_reversion":
        return 1 if f.rsi14 is not None and f.rsi14 <= p["low"] else -1 if f.rsi14 is not None and f.rsi14 >= p["high"] else 0
    if family == "rsi_momentum":
        return 1 if f.rsi14 is not None and f.rsi14 >= p["high"] else -1 if f.rsi14 is not None and f.rsi14 <= p["low"] else 0
    if family == "bollinger_reversion":
        width = p["std"] * x["std"]
        return 1 if close < x["sma"] - width else -1 if close > x["sma"] + width else 0
    if family == "bollinger_breakout":
        width = p["std"] * x["std"]
        return 1 if close > x["sma"] + width else -1 if close < x["sma"] - width else 0
    if family == "donchian":
        period = int(p["period"])
        prior = [b.close for b in bars[max(0, index - period):index]]
        return 1 if prior and close > max(prior) else -1 if prior and close < min(prior) else 0
    if family == "roc_momentum":
        period = int(p["period"])
        roc = close / bars[index - period].close - 1 if index >= period and bars[index - period].close else 0
        return 1 if roc >= p["threshold"] else -1 if roc <= -p["threshold"] else 0
    if family == "volume_breakout":
        return 1 if x["volume_ratio"] >= p["ratio"] and (f.return_1d or 0) > 0 else -1 if x["volume_ratio"] >= p["ratio"] and (f.return_1d or 0) < 0 else 0
    if family == "atr_trend":
        move = close - bars[index - 1].close if index else 0
        return 1 if x["atr"] and move >= p["multiple"] * x["atr"] else -1 if x["atr"] and move <= -p["multiple"] * x["atr"] else 0
    if family == "stochastic":
        return 1 if x["stochastic"] <= p["low"] else -1 if x["stochastic"] >= p["high"] else 0
    if family == "cci":
        dev = (x["typical"] - x["sma"]) / (x["std"] or 1) * 100
        return 1 if dev >= p["threshold"] else -1 if dev <= -p["threshold"] else 0
    if family == "williams_r":
        value = x["stochastic"] - 100
        return 1 if value <= p["low"] else -1 if value >= p["high"] else 0
    if family == "obv_trend":
        return 1 if x["obv"] > 0 and close >= (prev.close if prev else close) else -1 if x["obv"] < 0 and prev and close < prev.close else 0
    if family == "vwap_reversion":
        deviation = close / x["vwap"] - 1 if x["vwap"] else 0
        return -1 if deviation >= p["threshold"] else 1 if deviation <= -p["threshold"] else 0
    if family == "triple_ma":
        values = [ctx.sma(int(p[key]), index) for key in ("fast", "medium", "slow")]
        return 1 if all(v is not None for v in values) and values[0] > values[1] > values[2] else -1 if all(v is not None for v in values) and values[0] < values[1] < values[2] else 0
    if family == "support_resistance":
        period = int(p["period"])
        prior = [b.close for b in bars[max(0, index - period):index]]
        if not prior:
            return 0
        return 1 if close > max(prior) * (1 + p["buffer"]) else -1 if close < min(prior) * (1 - p["buffer"]) else 0
    if family == "price_action":
        return 1 if x["body_pct"] >= p["body"] and x["close_location"] >= p["close_location"] else -1 if x["body_pct"] >= p["body"] and x["close_location"] <= 1 - p["close_location"] else 0
    if family == "multi_confirmation":
        signals = [
            1 if f.sma20 is not None and close > f.sma20 else -1 if f.sma20 is not None else 0,
            1 if f.ema12 is not None and f.ema26 is not None and f.ema12 > f.ema26 else -1 if f.ema12 is not None and f.ema26 is not None else 0,
            1 if f.rsi14 is not None and f.rsi14 > 50 else -1 if f.rsi14 is not None else 0,
            1 if x["volume_ratio"] >= 1.2 and (f.return_1d or 0) > 0 else -1 if x["volume_ratio"] >= 1.2 and (f.return_1d or 0) < 0 else 0,
        ]
        score = sum(signals)
        return 1 if score >= int(p["required"]) else -1 if score <= -int(p["required"]) else 0
    return 0


def _train_strategy_scores(
    specs: Sequence[StrategySpec],
    bars: Sequence[Bar],
    features: Sequence[Feature],
    end_index: int,
    horizon: int,
    window: int,
    signal_matrix: dict[str, Sequence[int]] | None = None,
    min_train_index: int = 0,
    context: _IndicatorContext | None = None,
    prefix_stats: dict[str, dict[str, np.ndarray]] | None = None,
) -> dict[str, dict[str, float]]:
    start = max(min_train_index, end_index - window)
    stop = min(end_index - horizon, len(features) - horizon)
    stats: dict[str, dict[str, float]] = {}
    if prefix_stats is not None:
        for spec in specs:
            values = prefix_stats[spec.strategy_id]
            if stop <= start:
                samples = wins = 0
                signed_return = 0.0
            else:
                samples = int(values["samples"][stop] - values["samples"][start])
                wins = int(values["wins"][stop] - values["wins"][start])
                signed_return = float(
                    values["signed_return"][stop] - values["signed_return"][start]
                )
            stats[spec.strategy_id] = {
                "samples": float(samples),
                "win_rate": wins / samples if samples else 0.5,
                "edge": signed_return / samples if samples else 0.0,
            }
        return stats
    # A label is eligible only when its target date precedes the decision date.
    for spec in specs:
        returns: list[float] = []
        wins = 0
        for index in range(start, stop):
            signal = (
                signal_matrix[spec.strategy_id][index]
                if signal_matrix is not None
                else _signal(spec, bars, features, index, context)
            )
            if signal == 0:
                continue
            future = features[index].future_return_5d if horizon == 5 else (
                bars[index + horizon].close / bars[index].close - 1
                if index + horizon < len(bars) else None
            )
            if future is None:
                continue
            signed = signal * float(future)
            returns.append(signed)
            wins += int(signed > 0)
        stats[spec.strategy_id] = {
            "samples": float(len(returns)),
            "win_rate": wins / len(returns) if returns else 0.5,
            "edge": float(np.mean(returns)) if returns else 0.0,
        }
    return stats


def _build_signal_matrix(
    specs: Sequence[StrategySpec],
    bars: Sequence[Bar],
    features: Sequence[Feature],
    context: _IndicatorContext,
) -> dict[str, Sequence[int]]:
    return {
        spec.strategy_id: [
            _signal(spec, bars, features, index, context)
            for index in range(len(bars))
        ]
        for spec in specs
    }


def _build_prefix_stats(
    specs: Sequence[StrategySpec],
    bars: Sequence[Bar],
    features: Sequence[Feature],
    signal_matrix: dict[str, Sequence[int]],
    horizon: int,
) -> dict[str, dict[str, np.ndarray]]:
    """Build O(1)-query outcome statistics for each strategy/date range."""

    n = len(bars)
    if horizon == 5:
        future = np.asarray(
            [
                float(item.future_return_5d)
                if item.future_return_5d is not None
                else 0.0
                for item in features
            ],
            dtype=float,
        )
        valid_future = np.asarray(
            [item.future_return_5d is not None for item in features],
            dtype=bool,
        )
    else:
        future = np.zeros(n, dtype=float)
        valid_future = np.zeros(n, dtype=bool)
        for index in range(n - horizon):
            if bars[index].close:
                future[index] = bars[index + horizon].close / bars[index].close - 1.0
                valid_future[index] = True

    result: dict[str, dict[str, np.ndarray]] = {}
    for spec in specs:
        signals = np.asarray(signal_matrix[spec.strategy_id], dtype=float)
        valid = (signals != 0) & valid_future
        signed = np.where(valid, signals * future, 0.0)
        samples = np.where(valid, 1, 0).astype(np.int64)
        wins = np.where(valid & (signed > 0), 1, 0).astype(np.int64)
        result[spec.strategy_id] = {
            "samples": np.concatenate(([0], np.cumsum(samples, dtype=np.int64))),
            "wins": np.concatenate(([0], np.cumsum(wins, dtype=np.int64))),
            "signed_return": np.concatenate(([0.0], np.cumsum(signed, dtype=float))),
        }
    return result


def _posthoc_strategy_statistics(
    specs: Sequence[StrategySpec],
    prefix_stats: dict[str, dict[str, np.ndarray]],
    *,
    start: int,
    stop: int,
) -> list[dict[str, Any]]:
    """Rank every variant on the unseen decision interval only."""

    ranked: list[dict[str, Any]] = []
    for spec in specs:
        values = prefix_stats[spec.strategy_id]
        samples = int(values["samples"][stop] - values["samples"][start]) if stop > start else 0
        wins = int(values["wins"][stop] - values["wins"][start]) if stop > start else 0
        signed_return = (
            float(values["signed_return"][stop] - values["signed_return"][start])
            if stop > start else 0.0
        )
        ranked.append(
            {
                "strategy_id": spec.strategy_id,
                "samples": samples,
                "wins": wins,
                "win_rate_pct": round(wins / samples * 100, 4) if samples else None,
                "signed_return_pct": round(signed_return * 100, 4),
                "name": spec.name,
                "family": spec.family,
            }
        )
    ranked.sort(
        key=lambda item: (item["signed_return_pct"], item["win_rate_pct"] or 0),
        reverse=True,
    )
    return ranked


def _ensemble_vote(
    specs: Sequence[StrategySpec],
    bars: Sequence[Bar],
    features: Sequence[Feature],
    index: int,
    scores: dict[str, dict[str, float]],
    *,
    signal_matrix: dict[str, Sequence[int]] | None = None,
    context: _IndicatorContext | None = None,
) -> tuple[str, float, list[tuple[StrategySpec, int, float, dict[str, float]]]]:
    """Select the positive-edge strategy ensemble for one decision date."""

    current_signals = []
    for spec in specs:
        signal = (
            signal_matrix[spec.strategy_id][index]
            if signal_matrix is not None
            else _signal(spec, bars, features, index, context)
        )
        score = scores[spec.strategy_id]
        current_signals.append((spec, signal, score["edge"], score))
    active = [
        item for item in current_signals
        if item[1] != 0 and item[3]["samples"] > 0 and item[2] > 0
    ]
    # Cold-start period: before the first realized labels exist, use an
    # equal-weight vote from currently firing strategies.  No future
    # outcome is used to manufacture a score.
    if not active:
        active = [
            (spec, signal, 1.0, {"samples": 0, "win_rate": 0.5, "edge": 1.0})
            for spec, signal, _, _ in current_signals
            if signal != 0
        ]
    active.sort(key=lambda item: (item[2], item[3]["win_rate"]), reverse=True)
    selected = active[:10]
    denominator = sum(item[2] for item in selected) or 1.0
    vote = sum(item[1] * item[2] for item in selected) / denominator
    decision = "UP" if vote >= 0.15 else "DOWN" if vote <= -0.15 else "NEUTRAL"
    return decision, vote, selected


def latest_strategy_decision(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str = "",
    initial_history: int = 20,
    horizon: int = 5,
    training_window: int | None = None,
) -> dict[str, Any]:
    """Calculate one current-date ensemble decision without future leakage.

    This is the lightweight live counterpart of :func:`walk_forward_exam`.
    It uses all labels whose reveal date is before the requested decision date,
    then emits the selected strategy path and indicator snapshot.
    """

    bars = bars_from_rows(rows)
    features = build_features(bars, horizon=5)
    specs = strategy_catalog()
    if len(bars) <= initial_history:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "symbol": symbol,
            "bars": len(bars),
            "required_bars": initial_history + horizon + 1,
            "strategy_count": len(specs),
        }
    index = len(bars) - 1
    window = training_window or initial_history
    context = _IndicatorContext(bars, features)
    signal_matrix = _build_signal_matrix(specs, bars, features, context)
    prefix_stats = _build_prefix_stats(
        specs,
        bars,
        features,
        signal_matrix,
        horizon,
    )
    # Only the training window and current date are needed for a live call.
    scores = _train_strategy_scores(
        specs,
        bars,
        features,
        index,
        horizon,
        window,
        signal_matrix,
        min_train_index=0,
        context=context,
        prefix_stats=prefix_stats,
    )
    decision, vote, selected = _ensemble_vote(
        specs,
        bars,
        features,
        index,
        scores,
        signal_matrix=signal_matrix,
        context=context,
    )
    return {
        "status": "READY",
        "symbol": symbol,
        "date": bars[index].date,
        "decision": decision,
        "confidence": round(min(1.0, abs(vote)), 6),
        "visible_history_bars": index + 1,
        "training_feature_start": bars[max(0, index - window)].date,
        "training_feature_end": (
            bars[index - horizon - 1].date
            if index - horizon - 1 >= 0
            else None
        ),
        "training_label_end": (
            bars[index - 1].date
            if index - 1 >= horizon
            else None
        ),
        "outcome_revealed_at": None,
        "outcome_status": "PENDING",
        "selected_strategies": [
            {
                "id": item[0].strategy_id,
                "name": item[0].name,
                "family": item[0].family,
                "parameters": item[0].parameters,
                "signal": item[1],
                "edge": round(item[2], 8),
                "win_rate": round(item[3]["win_rate"], 4),
                "samples": int(item[3].get("samples", 0)),
            }
            for item in selected
        ],
        "indicators": {
            key: getattr(features[index], key)
            for key in (
                "close", "sma20", "sma50", "ema12", "ema26", "rsi14",
                "macd", "macd_signal", "atr14", "volume_ratio20",
            )
        },
        "protocol": {
            "decision_uses_future_fields": False,
            "future_labels_used_only_after_decision": True,
            "horizon_bars": horizon,
            "initial_history_bars": initial_history,
            "training_window_bars": window,
        },
    }


def _metrics(decisions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [item for item in decisions if item.get("outcome") in {"WIN", "LOSS", "FLAT"}]
    active = [item for item in evaluated if item.get("decision") != "NEUTRAL"]
    wins = sum(item["outcome"] == "WIN" for item in active)
    returns = [
        float(
            item.get("strategy_return")
            if item.get("strategy_return") is not None
            else float(item["realized_return"])
            * (1.0 if item.get("decision") == "UP" else -1.0)
        )
        for item in active
        if item.get("realized_return") is not None
    ]
    curve = 0.0
    peak = 0.0
    drawdown = 0.0
    compounded_equity = 1.0
    compounded_peak = 1.0
    compounded_drawdown = 0.0
    for value in returns:
        curve += value
        peak = max(peak, curve)
        drawdown = min(drawdown, curve - peak)
        compounded_equity *= 1.0 + value
        compounded_peak = max(compounded_peak, compounded_equity)
        if compounded_peak:
            compounded_drawdown = min(
                compounded_drawdown,
                compounded_equity / compounded_peak - 1.0,
            )
    return {
        "decisions": len(decisions),
        "evaluated": len(evaluated),
        "active_signals": len(active),
        "neutral_decisions": sum(item.get("decision") == "NEUTRAL" for item in decisions),
        "pending_outcomes": sum(
            item.get("realized_return") is None and item.get("outcome") is None
            for item in decisions
        ),
        "wins": wins,
        "losses": sum(item["outcome"] == "LOSS" for item in active),
        "flats": sum(item["outcome"] == "FLAT" for item in active),
        "win_rate_pct": round(wins / len(active) * 100, 4) if active else None,
        "mean_return_pct": round(float(np.mean(returns)) * 100, 4) if returns else None,
        "mean_strategy_return_pct": round(float(np.mean(returns)) * 100, 4) if returns else None,
        # The decision periods overlap by the five-day horizon, so these are
        # research diagnostics rather than an investable portfolio return.
        "cumulative_return_pct": round(curve * 100, 4),
        "max_drawdown_pct": round(drawdown * 100, 4),
        "overlapping_compounded_return_pct": round((compounded_equity - 1.0) * 100, 4),
        "overlapping_compounded_max_drawdown_pct": round(compounded_drawdown * 100, 4),
    }


def build_learning_summary(exam: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, persistent feedback artifact from an exam result.

    The summary deliberately keeps the decision timeline and strategy-level
    feedback separate.  It can be loaded on the next run for inspection or
    model governance, while the walk-forward selector itself still only uses
    labels that were available before each simulated decision.
    """

    decisions = [
        item for item in (exam.get("decisions") or [])
        if isinstance(item, dict)
    ]
    family_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    failure_by_reason: Counter[str] = Counter()
    confidence_buckets: dict[str, Counter[str]] = defaultdict(Counter)
    for decision in decisions:
        outcome = decision.get("outcome")
        if outcome not in {"WIN", "LOSS", "FLAT"}:
            continue
        realized = decision.get("realized_return")
        if outcome == "LOSS":
            if decision.get("decision") == "UP" and isinstance(realized, (int, float)) and realized < 0:
                reason = "up_direction_failed"
            elif decision.get("decision") == "DOWN" and isinstance(realized, (int, float)) and realized > 0:
                reason = "down_direction_failed"
            else:
                reason = "risk_or_execution_review"
            failure_by_reason[reason] += 1
        confidence = float(decision.get("confidence") or 0.0)
        bucket = "low" if confidence < 0.25 else "medium" if confidence < 0.55 else "high"
        confidence_buckets[bucket][outcome] += 1
        for selected in decision.get("selected_strategies") or []:
            family = str(selected.get("family") or "unknown")
            family_outcomes[family][outcome] += 1

    statistics = exam.get("strategy_statistics")
    if not isinstance(statistics, list):
        statistics = exam.get("leaderboard") or []
    return {
        "schema_version": "1.0",
        "type": "strategy_learning_summary",
        "symbol": exam.get("symbol", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_exam": {
            "status": exam.get("status"),
            "bars": exam.get("bars"),
            "range": exam.get("range"),
            "strategy_count": exam.get("strategy_count"),
            "protocol": exam.get("protocol"),
        },
        "metrics": exam.get("metrics") or {},
        "strategy_statistics": statistics,
        "failure_diagnostics": {
            "losses_by_reason": dict(failure_by_reason),
            "outcomes_by_family": {
                family: dict(counts)
                for family, counts in sorted(family_outcomes.items())
            },
            "outcomes_by_confidence": {
                bucket: dict(counts)
                for bucket, counts in sorted(confidence_buckets.items())
            },
        },
        "next_run_rule": (
            "Use only labels whose reveal date is earlier than the next decision; "
            "keep this artifact for audit and strategy governance."
        ),
    }


def walk_forward_exam(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str = "",
    initial_history: int = 20,
    evaluation_window: int = 30,
    horizon: int = 5,
    training_window: int | None = None,
    max_decisions: int = 0,
) -> dict[str, Any]:
    """Simulate learning day by day: first 20 observations, then 30 unseen."""

    bars = bars_from_rows(rows)
    if horizon != 5:
        # ``Feature.future_return_5d`` is fixed by the established indicator
        # contract; arbitrary horizons still work through direct bar labels.
        features = build_features(bars, horizon=5)
    else:
        features = build_features(bars, horizon=5)
    specs = strategy_catalog()
    if len(bars) <= initial_history:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "symbol": symbol,
            "bars": len(bars),
            "required_bars": initial_history + horizon + 1,
            "strategy_count": len(specs),
        }
    window = training_window or initial_history
    # Compute each strategy/date signal once.  Training windows revisit the
    # same historical dates many times; caching keeps the 200-strategy exam
    # practical for a full TSETMC history.
    context = _IndicatorContext(bars, features)
    signal_matrix = _build_signal_matrix(specs, bars, features, context)
    prefix_stats = _build_prefix_stats(
        specs,
        bars,
        features,
        signal_matrix,
        horizon,
    )
    decisions: list[dict[str, Any]] = []
    start = initial_history
    stop = len(bars) if max_decisions <= 0 else min(len(bars), start + max_decisions)
    for index in range(start, stop):
        scores = _train_strategy_scores(
            specs,
            bars,
            features,
            index,
            horizon,
            window,
            signal_matrix,
            min_train_index=0,
            prefix_stats=prefix_stats,
        )
        decision, vote, selected = _ensemble_vote(
            specs,
            bars,
            features,
            index,
            scores,
            signal_matrix=signal_matrix,
        )
        realized = None
        if index + horizon < len(bars):
            realized = bars[index + horizon].close / bars[index].close - 1
        strategy_return = None
        outcome = None
        if realized is not None and decision != "NEUTRAL":
            strategy_return = realized if decision == "UP" else -realized
            if abs(strategy_return) <= 1e-12:
                outcome = "FLAT"
            else:
                outcome = "WIN" if strategy_return > 0 else "LOSS"
        reveal_at = (
            bars[index + horizon].date
            if index + horizon < len(bars)
            else None
        )
        record = {
            "date": bars[index].date,
            "decision": decision,
            "confidence": round(min(1.0, abs(vote)), 6),
            # A label is usable only after its horizon has elapsed.  Keep both
            # feature dates and target/reveal dates explicit for auditability.
            "training_feature_start": bars[max(0, index - window)].date,
            "training_feature_end": (
                bars[index - horizon - 1].date
                if index - horizon - 1 >= 0
                else None
            ),
            "training_label_start": (
                bars[max(0, index - window) + horizon].date
                if max(0, index - window) + horizon < index
                else None
            ),
            "training_label_end": (
                bars[index - 1].date
                if index - 1 >= horizon
                else None
            ),
            # Backward-compatible aliases used by earlier artifacts.
            "training_start": bars[max(0, index - window)].date,
            "training_end": (
                bars[index - 1].date
                if index - 1 >= horizon
                else None
            ),
            "feature_history_end": bars[index].date,
            "outcome_revealed_at": reveal_at,
            "outcome_status": "REVEALED" if reveal_at else "PENDING",
            "visible_history_bars": index + 1,
            "selected_strategies": [
                {
                    "id": item[0].strategy_id,
                    "name": item[0].name,
                    "family": item[0].family,
                    "parameters": item[0].parameters,
                    "signal": item[1],
                    "edge": round(item[2], 8),
                    "win_rate": round(item[3]["win_rate"], 4),
                }
                for item in selected
            ],
            "indicators": {
                key: getattr(features[index], key)
                for key in ("close", "sma20", "sma50", "ema12", "ema26", "rsi14", "macd", "macd_signal", "atr14", "volume_ratio20")
            },
            "realized_return": realized,
            "strategy_return": strategy_return,
            "outcome": outcome,
        }
        decisions.append(record)
    segments = []
    for offset in range(0, len(decisions), evaluation_window):
        chunk = decisions[offset:offset + evaluation_window]
        if chunk:
            segments.append({
                "segment": len(segments) + 1,
                "from": chunk[0]["date"],
                "to": chunk[-1]["date"],
                "metrics": _metrics(chunk),
            })
    ranked = _posthoc_strategy_statistics(
        specs,
        prefix_stats,
        start=start,
        stop=min(stop, len(bars) - horizon),
    )
    return {
        "status": "COMPLETE",
        "symbol": symbol,
        "method": "expanding/rolling point-in-time walk-forward",
        "protocol": {
            "initial_history_bars": initial_history,
            "evaluation_window_bars": evaluation_window,
            "horizon_bars": horizon,
            "training_window_bars": window,
            "decision_uses_future_fields": False,
            "future_labels_used_only_after_decision": True,
        },
        "bars": len(bars),
        "range": {"start": bars[0].date, "end": bars[-1].date},
        "strategy_count": len(specs),
        "catalog_families": sorted({spec.family for spec in specs}),
        "metrics": _metrics(decisions),
        "segments": segments,
        "leaderboard": ranked[:20],
        "strategy_statistics": ranked,
        "decisions": decisions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "StrategySpec",
    "bars_from_rows",
    "strategy_catalog",
    "strategy_definitions",
    "build_learning_summary",
    "latest_strategy_decision",
    "walk_forward_exam",
]
