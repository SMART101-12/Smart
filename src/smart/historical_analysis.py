"""Deterministic technical analysis over stored TSETMC daily history.

This module intentionally contains no trading recommendation logic. It turns
historical rows into transparent indicators that the ranking/risk layers can
consume later.
"""
from __future__ import annotations

from math import sqrt
from typing import Any


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[:period]) / period


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    chronological = list(reversed(values))
    ema = sum(chronological[:period]) / period
    alpha = 2 / (period + 1)
    for value in chronological[period:]:
        ema = alpha * value + (1 - alpha) * ema
    return ema


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    chronological = list(reversed(values))
    gains: list[float] = []
    losses: list[float] = []
    for prev, cur in zip(chronological, chronological[1:]):
        change = cur - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _annualized_volatility(values: list[float], period: int = 20) -> float | None:
    if len(values) < period + 1:
        return None
    chronological = list(reversed(values[: period + 1]))
    returns = [(cur / prev) - 1 for prev, cur in zip(chronological, chronological[1:]) if prev]
    if len(returns) < period:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((x - mean) ** 2 for x in returns) / len(returns)
    return sqrt(variance) * sqrt(252)


def analyze_history(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze rows ordered newest-first, as returned by TSETMC."""
    closes = [v for v in (_num(row, "pClosing", "pDrCotVal") for row in rows) if v is not None]
    volumes = [v for v in (_num(row, "qTotTran5J") for row in rows) if v is not None]
    if not closes:
        return {"status": "insufficient_data", "history_rows": len(rows)}

    latest = closes[0]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    ema20 = _ema(closes, 20)
    rsi14 = _rsi(closes, 14)
    vol20 = _annualized_volatility(closes, 20)
    avg_volume20 = sum(volumes[:20]) / min(len(volumes), 20) if volumes else None
    volume_ratio = (volumes[0] / avg_volume20) if volumes and avg_volume20 else None

    trend = "unknown"
    if sma20 is not None and sma50 is not None:
        trend = "bullish" if latest > sma20 > sma50 else "bearish" if latest < sma20 < sma50 else "mixed"

    return {
        "status": "ok",
        "history_rows": len(rows),
        "usable_close_rows": len(closes),
        "latest_close": latest,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "ema20": ema20,
        "rsi14": rsi14,
        "annualized_volatility20": vol20,
        "avg_volume20": avg_volume20,
        "latest_volume_ratio20": volume_ratio,
        "trend": trend,
        "data_requirements": {
            "sma200_available": sma200 is not None,
            "rsi_available": rsi14 is not None,
            "volatility_available": vol20 is not None,
        },
    }
