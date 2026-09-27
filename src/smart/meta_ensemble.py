"""Leakage-safe direction/magnitude meta-ensemble for daily stock history.

Design goals:
- separate direction from magnitude;
- regime-aware ensemble of diverse technical families;
- online meta-weights learned only from observations available before the signal;
- empirical probability calibration using only prior outcomes;
- volatility-scaled magnitude and confidence gate;
- optional triple-barrier labels for trade-oriented evaluation.

This module deliberately uses only the Python standard library so it can run in
SMART's lightweight runtime without adding a heavy ML dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import exp
from statistics import mean
from typing import Any


@dataclass
class Prediction:
    date: str
    price: float
    direction: str
    direction_probability: float
    magnitude_pct: float
    expected_price: float
    confidence: float
    regime: str
    gate: str
    components: dict[str, float]
    label: int | None = None
    future_return_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        try:
            value = row.get(key)
            if value not in (None, "", "-"):
                return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return default


def _sma(values: list[float], period: int) -> float | None:
    return mean(values[-period:]) if len(values) >= period else None


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    value = mean(values[:period])
    for item in values[period:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    window = changes[-period:]
    gains = sum(max(v, 0.0) for v in window) / period
    losses = sum(max(-v, 0.0) for v in window) / period
    return 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)


def _atr(rows: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(rows) < period:
        return None
    true_ranges: list[float] = []
    for i, row in enumerate(rows):
        high = _num(row, "pMax", "pClosing")
        low = _num(row, "pMin", "pClosing")
        if i == 0:
            true_ranges.append(max(high - low, 0.0))
            continue
        previous_close = _num(rows[i - 1], "pClosing", "pDrCotVal")
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(true_ranges[-period:])


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-max(-30.0, min(30.0, value))))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _features(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [_num(row, "pClosing", "pDrCotVal") for row in rows]
    volumes = [_num(row, "qTotTran5J") for row in rows]
    price = closes[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(rows, 14)
    volume20 = _sma(volumes, 20)
    rvol20 = volumes[-1] / volume20 if volume20 else None
    roc5 = price / closes[-6] - 1.0 if len(closes) >= 6 else None
    roc20 = price / closes[-21] - 1.0 if len(closes) >= 21 else None
    prior_high20 = max(closes[-21:-1]) if len(closes) >= 21 else None
    prior_low20 = min(closes[-21:-1]) if len(closes) >= 21 else None
    breakout = price / prior_high20 - 1.0 if prior_high20 else 0.0
    drawdown60 = price / max(closes[-60:]) - 1.0 if closes else 0.0
    atr_pct = atr14 / price if atr14 and price else None
    return locals()


def _component_scores(features: dict[str, Any]) -> dict[str, float]:
    price = features["price"]
    sma20, sma50, sma200 = features["sma20"], features["sma50"], features["sma200"]
    if sma20 and sma50:
        trend = _clamp(
            (price / sma20 - 1.0) * 8.0
            + (price / sma50 - 1.0) * 6.0
            + ((sma50 / sma200 - 1.0) * 4.0 if sma200 else 0.0),
            -1.0,
            1.0,
        )
    else:
        trend = 0.0
    if features["ema12"] and features["ema26"]:
        macd = _clamp((features["ema12"] / features["ema26"] - 1.0) * 80.0, -1.0, 1.0)
    else:
        macd = 0.0
    rsi14 = features["rsi14"]
    rsi_score = 0.0 if rsi14 is None else _clamp((rsi14 - 50.0) / 20.0, -1.0, 1.0)
    if features["roc5"] is not None and features["roc20"] is not None:
        roc = _clamp(features["roc5"] * 10.0 + features["roc20"] * 4.0, -1.0, 1.0)
    else:
        roc = 0.0
    breakout = _clamp(features["breakout"] * 30.0, -1.0, 1.0)
    volume = 0.0
    if features["rvol20"] is not None:
        signed = 1.0 if (features["roc5"] or 0.0) > 0 else -1.0 if (features["roc5"] or 0.0) < 0 else 0.0
        volume = _clamp((features["rvol20"] - 1.0) * 0.8 * signed, -1.0, 1.0)
    return {
        "trend": trend,
        "macd": macd,
        "rsi": rsi_score,
        "roc": roc,
        "breakout": breakout,
        "volume": volume,
    }


def _regime(features: dict[str, Any]) -> str:
    price, sma50, sma200 = features["price"], features["sma50"], features["sma200"]
    if not sma50 or not sma200:
        return "insufficient"
    if price > sma50 > sma200:
        return "bull"
    if price < sma50 < sma200:
        return "bear"
    return "sideways"


def triple_barrier_label(
    rows: list[dict[str, Any]],
    index: int,
    horizon: int = 5,
    profit_multiple: float = 1.25,
    stop_multiple: float = 1.0,
) -> int | None:
    """Return +1/-1/0 using ATR-scaled profit, stop and time barriers.

    When both barriers are touched by the same daily bar, the label is 0 rather
    than assuming an intraday order that daily OHLC cannot prove.
    """
    if index + horizon >= len(rows):
        return None
    history = rows[: index + 1]
    price = _num(rows[index], "pClosing", "pDrCotVal")
    atr14 = _atr(history, 14)
    if not price or not atr14:
        return None
    upper = price + profit_multiple * atr14
    lower = price - stop_multiple * atr14
    for j in range(index + 1, min(len(rows), index + horizon + 1)):
        high = _num(rows[j], "pMax", "pClosing")
        low = _num(rows[j], "pMin", "pClosing")
        hit_up = high >= upper
        hit_down = low <= lower
        if hit_up and hit_down:
            return 0
        if hit_up:
            return 1
        if hit_down:
            return -1
    future = _num(rows[index + horizon], "pClosing", "pDrCotVal")
    return 1 if future > price else -1 if future < price else 0


def _calibrate(raw_probability: float, history: list[tuple[float, int, float]]) -> float:
    """Calibrate probabilities from prior observations only using smoothed bins."""
    if len(history) < 30:
        return raw_probability
    bins: list[list[int]] = [[] for _ in range(10)]
    for probability, outcome, _ in history:
        bucket = min(9, max(0, int(probability * 10.0)))
        bins[bucket].append(outcome)
    bucket = min(9, max(0, int(raw_probability * 10.0)))
    outcomes = bins[bucket]
    if not outcomes:
        return raw_probability
    # Laplace smoothing avoids unstable 0/1 probabilities in sparse tails.
    return (sum(outcomes) + 2.0) / (len(outcomes) + 4.0)


def predict_at(
    rows: list[dict[str, Any]],
    index: int,
    calibration_history: list[tuple[float, int, float]] | None = None,
    component_history: dict[str, list[float]] | None = None,
) -> Prediction | None:
    history = rows[: index + 1]
    if len(history) < 50:
        return None
    features = _features(history)
    components = _component_scores(features)
    regime = _regime(features)

    weights = {"trend": 0.28, "macd": 0.14, "rsi": 0.14, "roc": 0.16, "breakout": 0.14, "volume": 0.14}
    if component_history:
        for name in weights:
            values = component_history.get(name, [])
            if len(values) >= 20:
                recent = values[-80:]
                hit_rate = sum(value > 0 for value in recent) / len(recent)
                weights[name] *= _clamp(0.5 + hit_rate, 0.65, 1.35)
    if regime == "sideways":
        weights["rsi"] *= 1.25
        weights["breakout"] *= 0.80
    elif regime == "bull":
        weights["trend"] *= 1.20
        weights["roc"] *= 1.10
    elif regime == "bear":
        weights["volume"] *= 1.15
        weights["trend"] *= 1.05

    denominator = sum(weights.values())
    score = sum(weights[name] * components[name] for name in weights) / denominator
    raw_probability = _sigmoid(2.4 * score)
    probability = _calibrate(raw_probability, calibration_history or [])
    direction = "UP" if probability >= 0.55 else "DOWN" if probability <= 0.45 else "NEUTRAL"

    price = features["price"]
    atr_pct = features["atr_pct"] or 0.0
    volatility_5d = atr_pct * 2.0
    conditional = []
    if calibration_history:
        conditional = [
            abs(item[2])
            for item in calibration_history[-120:]
            if (item[0] >= 0.55) == (probability >= 0.55)
        ]
    empirical = mean(conditional) if len(conditional) >= 10 else volatility_5d
    magnitude = _clamp(0.65 * volatility_5d + 0.35 * empirical, 0.003, 0.20)
    expected_price = price * (1.0 + magnitude if direction == "UP" else 1.0 - magnitude if direction == "DOWN" else 1.0)
    confidence = abs(probability - 0.5) * 2.0
    gate = "PASS" if ((direction == "UP" and probability >= 0.60) or (direction == "DOWN" and probability <= 0.40)) else "HOLD"

    return Prediction(
        date=str(rows[index].get("dEven", "")),
        price=price,
        direction=direction,
        direction_probability=round(probability, 6),
        magnitude_pct=round(magnitude * 100.0, 4),
        expected_price=round(expected_price, 4),
        confidence=round(confidence, 6),
        regime=regime,
        gate=gate,
        components={name: round(value, 6) for name, value in components.items()},
    )


def walk_forward(rows: list[dict[str, Any]], horizon: int = 5) -> list[Prediction]:
    """Generate predictions chronologically; no signal sees a future row."""
    ordered = sorted(rows, key=lambda row: int(row.get("dEven", 0)))
    predictions: list[Prediction] = []
    calibration_history: list[tuple[float, int, float]] = []
    component_history: dict[str, list[float]] = {name: [] for name in ("trend", "macd", "rsi", "roc", "breakout", "volume")}

    for index in range(50, len(ordered) - horizon):
        prediction = predict_at(ordered, index, calibration_history, component_history)
        if prediction is None:
            continue
        price = _num(ordered[index], "pClosing", "pDrCotVal")
        future_price = _num(ordered[index + horizon], "pClosing", "pDrCotVal")
        future_return = future_price / price - 1.0 if price else 0.0
        prediction.future_return_pct = round(future_return * 100.0, 6)
        prediction.label = triple_barrier_label(ordered, index, horizon)
        predictions.append(prediction)

        outcome = 1 if future_return > 0 else 0
        calibration_history.append((prediction.direction_probability, outcome, future_return))
        for name, value in prediction.components.items():
            component_history[name].append(value * (1.0 if future_return > 0 else -1.0))
    return predictions


def evaluate(predictions: list[Prediction]) -> dict[str, Any]:
    active = [prediction for prediction in predictions if prediction.direction != "NEUTRAL"]
    correct = [
        prediction for prediction in active
        if (prediction.direction == "UP" and (prediction.future_return_pct or 0.0) > 0)
        or (prediction.direction == "DOWN" and (prediction.future_return_pct or 0.0) < 0)
    ]
    brier = mean([
        (prediction.direction_probability - (1 if (prediction.future_return_pct or 0.0) > 0 else 0)) ** 2
        for prediction in active
    ]) if active else None
    strategy_returns = [
        (prediction.future_return_pct or 0.0) * (1.0 if prediction.direction == "UP" else -1.0)
        for prediction in active
    ]
    gated = [prediction for prediction in active if prediction.gate == "PASS"]
    gated_returns = [
        (prediction.future_return_pct or 0.0) * (1.0 if prediction.direction == "UP" else -1.0)
        for prediction in gated
    ]
    return {
        "predictions": len(predictions),
        "signals": len(active),
        "accuracy": round(len(correct) / len(active), 6) if active else None,
        "brier": round(brier, 6) if brier is not None else None,
        "coverage": round(len(active) / len(predictions), 6) if predictions else 0.0,
        "avg_strategy_return_5d_pct": round(mean(strategy_returns), 6) if strategy_returns else None,
        "gate_signals": len(gated),
        "gate_avg_strategy_return_5d_pct": round(mean(gated_returns), 6) if gated_returns else None,
        "gate_win_rate": round(sum(value > 0 for value in gated_returns) / len(gated_returns), 6) if gated_returns else None,
        "triple_barrier_nonzero_rate": round(
            sum(prediction.label not in (None, 0) for prediction in predictions) / len(predictions), 6
        ) if predictions else 0.0,
    }


def compare_legacy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate SMART's existing technical score on the same 5-day target."""
    from .technical_analysis import Bar, build_features

    bars = [
        Bar(
            date=str(row.get("dEven", "")),
            close=_num(row, "pClosing", "pDrCotVal"),
            high=_num(row, "pMax", "pClosing"),
            low=_num(row, "pMin", "pClosing"),
            open=_num(row, "pFirst", "pClosing"),
            volume=_num(row, "qTotTran5J"),
            value=_num(row, "qTotCap"),
            trades=_num(row, "zTotTran"),
        )
        for row in sorted(rows, key=lambda item: int(item.get("dEven", 0)))
    ]
    features = build_features(bars, 5)
    active = [feature for feature in features if feature.prediction != "NEUTRAL" and feature.prediction_correct is not None]
    return {
        "signals": len(active),
        "accuracy": round(sum(bool(feature.prediction_correct) for feature in active) / len(active), 6) if active else None,
    }
