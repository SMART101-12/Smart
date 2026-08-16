"""Point-in-time daily price forecasting with online walk-forward learning.

This is deliberately deterministic and auditable. It does not use future rows
when generating a forecast. Each expert is evaluated only after its forecast
has been written, then its weight is updated from the realized next close.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from .technical import ema, rsi, sma

ENGINE_VERSION = "daily-prediction-v1.0"
EXPERTS = ("naive", "sma20", "ema20", "momentum5", "trend20")


def _close(row: dict[str, Any]) -> float | None:
    for key in ("pClosing", "pDrCotVal"):
        try:
            value = float(row.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            d = int(row.get("dEven"))
        except (TypeError, ValueError):
            continue
        if _close(row) is not None:
            unique[d] = row
    return [unique[d] for d in sorted(unique)]


def load_git_history(root: Path, symbol: str) -> list[dict[str, Any]]:
    """Load every monthly history file from Git working tree."""
    directory = root / "runtime" / "history" / symbol
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            rows.extend(payload.get("daily_history", []))
    return normalize_rows(rows)


def _trend_projection(closes: list[float], window: int = 20) -> float | None:
    if len(closes) < window:
        return None
    y = closes[-window:]
    x_mean = (window - 1) / 2
    y_mean = mean(y)
    denom = sum((i - x_mean) ** 2 for i in range(window))
    slope = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(y)) / denom
    return max(0.01, y[-1] + slope)


def _experts(closes: list[float]) -> dict[str, float]:
    last = closes[-1]
    result = {"naive": last}
    s20 = sma(closes, 20)
    e20 = ema(closes, 20)
    if s20 is not None:
        result["sma20"] = s20
    if e20 is not None:
        result["ema20"] = e20
    if len(closes) >= 6:
        avg_return = mean((closes[i] / closes[i - 1]) - 1 for i in range(len(closes) - 5, len(closes)))
        result["momentum5"] = max(0.01, last * (1 + avg_return))
    trend = _trend_projection(closes)
    if trend is not None:
        result["trend20"] = trend
    return result


def _normalize(weights: dict[str, float], available: dict[str, float]) -> dict[str, float]:
    total = sum(weights[k] for k in available if k in weights)
    if total <= 0:
        n = len(available)
        return {k: 1 / n for k in available}
    return {k: weights[k] / total for k in available}


def _forecast(experts: dict[str, float], weights: dict[str, float]) -> float:
    w = _normalize(weights, experts)
    return sum(experts[k] * w[k] for k in experts)


def _update(weights: dict[str, float], experts: dict[str, float], actual: float, *, rate: float = 1.5) -> None:
    """Exponentially penalize experts by absolute percentage error."""
    for name, prediction in experts.items():
        error = abs(prediction / actual - 1.0) if actual else 1.0
        weights[name] *= math.exp(-rate * min(error, 0.25))
    _normalize_in_place(weights)


def _normalize_in_place(weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if total <= 0:
        n = len(weights)
        for k in weights:
            weights[k] = 1 / n
    else:
        for k in weights:
            weights[k] /= total


def _recursive_five_day(closes: list[float], weights: dict[str, float]) -> list[float]:
    work = list(closes)
    path: list[float] = []
    for _ in range(5):
        experts = _experts(work)
        prediction = _forecast(experts, weights)
        path.append(prediction)
        work.append(prediction)
    return path


def _features(closes: list[float], volumes: list[float]) -> dict[str, Any]:
    last = closes[-1]
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    s200 = sma(closes, 200)
    rsi14 = rsi(closes, 14)
    e20 = ema(closes, 20)
    vol20 = sma(volumes, 20) if len(volumes) >= 20 else None
    latest_volume = volumes[-1] if volumes else None
    return {
        "price": last,
        "sma20": s20,
        "sma50": s50,
        "sma200": s200,
        "ema20": e20,
        "rsi14": rsi14,
        "rvol20": (latest_volume / vol20) if latest_volume and vol20 else None,
        "regime": (
            "bull" if s50 is not None and s200 is not None and last > s50 > s200
            else "bear" if s50 is not None and s200 is not None and last < s50 < s200
            else "sideways"
        ),
    }


@dataclass
class Prediction:
    date: int
    next_date: int
    actual_price: float | None
    predicted_price: float
    predicted_return_pct: float
    actual_return_pct: float | None
    direction_correct: bool | None
    baseline_error_pct: float | None
    model_error_pct: float | None
    improvement_vs_naive_pct: float | None
    confidence: float
    expert_weights: dict[str, float]
    expert_predictions: dict[str, float]
    five_day_forecast: list[float]
    features: dict[str, Any]
    error_class: str | None


def run_walk_forward(rows: list[dict[str, Any]], min_history: int = 30) -> dict[str, Any]:
    rows = normalize_rows(rows)
    if len(rows) <= min_history + 1:
        raise ValueError("not enough historical rows for walk-forward prediction")

    weights = {name: 1.0 for name in EXPERTS}
    predictions: list[dict[str, Any]] = []
    learning_log: list[dict[str, Any]] = []

    for i in range(min_history, len(rows) - 1):
        history = rows[: i + 1]
        closes = [_close(r) for r in history]
        closes = [v for v in closes if v is not None]
        volumes = []
        for r in history:
            try:
                volumes.append(float(r.get("qTotTran5J", 0)))
            except (TypeError, ValueError):
                volumes.append(0.0)
        experts = _experts(closes)
        active_weights = _normalize(dict(weights), experts)
        predicted = _forecast(experts, active_weights)
        current = closes[-1]
        actual = _close(rows[i + 1])
        actual_return = ((actual / current) - 1) * 100 if actual and current else None
        predicted_return = ((predicted / current) - 1) * 100 if current else 0.0
        model_error = abs(predicted / actual - 1) * 100 if actual else None
        naive = experts["naive"]
        baseline_error = abs(naive / actual - 1) * 100 if actual else None
        improvement = ((baseline_error - model_error) / baseline_error * 100) if baseline_error and model_error is not None else None
        direction_correct = ((predicted >= current) == (actual >= current)) if actual else None
        dispersion = max(experts.values()) - min(experts.values()) if experts else 0
        confidence = max(0.0, min(1.0, 1.0 - dispersion / max(current, 1e-9)))
        error_class = None
        if actual is not None:
            if model_error > 5:
                regime = _features(closes, volumes)["regime"]
                error_class = "regime_or_gap" if regime in {"bull", "bear"} else "model_dispersion"
            elif improvement is not None and improvement < 0:
                error_class = "naive_better"
            else:
                error_class = "within_tolerance"

        five_day = _recursive_five_day(closes, active_weights)
        row = Prediction(
            date=int(rows[i]["dEven"]),
            next_date=int(rows[i + 1]["dEven"]),
            actual_price=actual,
            predicted_price=predicted,
            predicted_return_pct=predicted_return,
            actual_return_pct=actual_return,
            direction_correct=direction_correct,
            baseline_error_pct=baseline_error,
            model_error_pct=model_error,
            improvement_vs_naive_pct=improvement,
            confidence=confidence,
            expert_weights=active_weights,
            expert_predictions=experts,
            five_day_forecast=five_day,
            features=_features(closes, volumes),
            error_class=error_class,
        )
        predictions.append(row.__dict__)

        before = dict(weights)
        _update(weights, experts, actual)
        learning_log.append({
            "date": int(rows[i]["dEven"]),
            "next_date": int(rows[i + 1]["dEven"]),
            "weights_before": before,
            "weights_after": dict(weights),
            "model_error_pct": model_error,
            "baseline_error_pct": baseline_error,
            "improvement_vs_naive_pct": improvement,
            "error_class": error_class,
        })

    valid = [p for p in predictions if p["model_error_pct"] is not None]
    direction = [p for p in valid if p["direction_correct"] is not None]
    model_errors = [p["model_error_pct"] for p in valid]
    baseline_errors = [p["baseline_error_pct"] for p in valid]
    improvements = [p["improvement_vs_naive_pct"] for p in valid if p["improvement_vs_naive_pct"] is not None]

    return {
        "engine_version": ENGINE_VERSION,
        "symbol": "پالایش",
        "rows": len(rows),
        "first_date": rows[0].get("dEven"),
        "last_date": rows[-1].get("dEven"),
        "min_history": min_history,
        "no_lookahead": True,
        "prediction_count": len(predictions),
        "metrics": {
            "direction_accuracy_pct": round(sum(p["direction_correct"] for p in direction) / len(direction) * 100, 4) if direction else None,
            "mae_pct": round(mean(model_errors), 4) if model_errors else None,
            "baseline_naive_mae_pct": round(mean(baseline_errors), 4) if baseline_errors else None,
            "mean_improvement_vs_naive_pct": round(mean(improvements), 4) if improvements else None,
            "model_beats_naive_pct": round(sum(x > 0 for x in improvements) / len(improvements) * 100, 4) if improvements else None,
        },
        "final_weights": weights,
        "predictions": predictions,
        "learning_log": learning_log,
    }
