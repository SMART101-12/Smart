"""Historical, point-in-time stock DNA and regime/strategy evaluation.

History from TSETMC is normally newest-first. This module normalizes it to
oldest-first before any rolling calculation and never uses future rows for a
point-in-time analysis.
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


def normalize_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return daily history oldest-first, without mutating the input."""
    return sorted(rows, key=lambda r: int(r.get("dEven", 0)))


def _num(row: dict[str, Any], key: str) -> float | None:
    try:
        v = row.get(key)
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _sma(values: list[float], n: int) -> float | None:
    return mean(values[-n:]) if len(values) >= n else None


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
    """Analyze one date using rows up to and including end_index only."""
    rows = normalize_history(rows)
    history = rows[: end_index + 1]
    closes = [v for r in history if (v := _num(r, "pClosing")) is not None]
    volumes = [v for r in history if (v := _num(r, "qTotTran5J")) is not None]
    if not closes:
        return {"status": "insufficient_data", "point_in_time": True}

    price = closes[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    rsi14 = _rsi(closes, 14)
    vol20 = _sma(volumes, 20)
    latest_volume = volumes[-1] if volumes else None
    rvol = latest_volume / vol20 if vol20 else None

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
    if sma20 is not None and sma50 is not None:
        trend_score = 80.0 if price > sma20 > sma50 else 20.0 if price < sma20 < sma50 else 50.0
        signals.append(SignalResult("trend_following", trend_score, "price/SMA20/SMA50 alignment"))
    if rsi14 is not None:
        momentum_score = 75.0 if 50 <= rsi14 <= 70 else 65.0 if rsi14 > 70 else 35.0 if rsi14 < 30 else 50.0
        signals.append(SignalResult("momentum_rsi", momentum_score, f"RSI14={rsi14:.1f}"))
    if rvol is not None:
        volume_score = 75.0 if rvol >= 1.5 else 60.0 if rvol >= 1.0 else 45.0
        signals.append(SignalResult("volume_confirmation", volume_score, f"RVOL20={rvol:.2f}"))

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
        "latest_volume": latest_volume,
        "rvol20": rvol,
        "strategy_signals": [s.__dict__ for s in signals],
        "smart_score": round(score, 2),
        "point_in_time": True,
    }
