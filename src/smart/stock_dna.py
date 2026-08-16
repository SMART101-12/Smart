"""Historical, point-in-time stock DNA and regime/strategy evaluation.

No future observations are allowed in calculations for a given market date.
This module provides the first deterministic foundation for per-symbol learning.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass
class SignalResult:
    strategy: str
    score: float
    reason: str


def _close(row: dict[str, Any]) -> float | None:
    v = row.get("pClosing")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _volume(row: dict[str, Any]) -> float | None:
    v = row.get("qTotTran5J")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return mean(values[-n:])


def _rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) <= n:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    window = changes[-n:]
    gains = sum(max(x, 0.0) for x in window) / n
    losses = sum(max(-x, 0.0) for x in window) / n
    if losses == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def point_in_time_analysis(rows: list[dict[str, Any]], end_index: int) -> dict[str, Any]:
    """Analyze one date using rows[0:end_index+1] only."""
    history = rows[: end_index + 1]
    closes = [v for r in history if (v := _close(r)) is not None]
    volumes = [v for r in history if (v := _volume(r)) is not None]
    if not closes:
        return {"status": "insufficient_data"}

    price = closes[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    rsi14 = _rsi(closes, 14)
    vol20 = _sma(volumes, 20)
    rvol = volumes[-1] / vol20 if vol20 else None

    if sma50 is not None and sma200 is not None:
        if price > sma50 > sma200:
            regime = "bull"
        elif price < sma50 < sma200:
            regime = "bear"
        else:
            regime = "sideways"
    else:
        regime = "insufficient_history"

    signals: list[SignalResult] = []
    if sma20 and sma50:
        trend_score = 80.0 if price > sma20 > sma50 else 20.0 if price < sma20 < sma50 else 50.0
        signals.append(SignalResult("trend_following", trend_score, "price/SMA20/SMA50 alignment"))
    if rsi14 is not None:
        momentum_score = 75.0 if 50 <= rsi14 <= 70 else 65.0 if rsi14 > 70 else 35.0 if rsi14 < 30 else 50.0
        signals.append(SignalResult("momentum_rsi", momentum_score, f"RSI14={rsi14:.1f}"))
    if rvol is not None:
        volume_score = 75.0 if rvol >= 1.5 else 60.0 if rvol >= 1.0 else 45.0
        signals.append(SignalResult("volume_confirmation", volume_score, f"RVOL20={rvol:.2f}"))

    # Regime-aware weighting, intentionally transparent and adjustable.
    weights = {
        "bull": {"trend_following": 0.45, "momentum_rsi": 0.25, "volume_confirmation": 0.30},
        "sideways": {"trend_following": 0.25, "momentum_rsi": 0.45, "volume_confirmation": 0.30},
        "bear": {"trend_following": 0.35, "momentum_rsi": 0.25, "volume_confirmation": 0.40},
    }
    active = weights.get(regime, {})
    score = sum(s.score * active.get(s.strategy, 0.0) for s in signals)

    return {
        "status": "ok",
        "market_date": history[-1].get("dEven"),
        "regime": regime,
        "price": price,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "rsi14": rsi14,
        "volume20": vol20,
        "rvol20": rvol,
        "strategy_signals": [s.__dict__ for s in signals],
        "smart_score": round(score, 2),
        "point_in_time": True,
    }
