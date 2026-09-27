"""Causal equity indicators; warm-up values remain null, never backfilled."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from smart.strategy_lab import bars_from_rows
from smart.technical_analysis import atr, ema, rsi, sma


def finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def indicator_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    bars = bars_from_rows(rows)
    frame = pd.DataFrame({"close": [b.close for b in bars], "high": [b.high for b in bars],
                          "low": [b.low for b in bars], "volume": [b.volume for b in bars]})
    c, h, l, v = (frame[k] for k in ("close", "high", "low", "volume"))
    out = pd.DataFrame({"date": [b.date for b in bars], "close": c})
    for n in (5, 10, 20, 50, 100, 200):
        out[f"sma{n}"] = sma(c.tolist(), n)
        out[f"ema{n}"] = ema(c.tolist(), n)
    out["rsi14"] = rsi(c.tolist(), 14)
    out["macd"] = pd.Series(ema(c.tolist(), 12)) - pd.Series(ema(c.tolist(), 26))
    out["macd_signal"] = ema([finite(x) for x in out.macd], 9)
    out["macd_histogram"] = out.macd - out.macd_signal
    span = (h.rolling(14).max() - l.rolling(14).min()).replace(0, np.nan)
    out["stochastic_k"] = 100 * (c - l.rolling(14).min()) / span
    out["stochastic_d"] = out.stochastic_k.rolling(3).mean()
    out["williams_r"] = -100 * (h.rolling(14).max() - c) / span
    out["roc20"] = c.pct_change(20, fill_method=None) * 100
    typical = (h + l + c) / 3
    deviation = typical.rolling(20).apply(lambda x: float(np.mean(np.abs(x - np.mean(x)))))
    out["cci20"] = (typical - typical.rolling(20).mean()) / (0.015 * deviation.replace(0, np.nan))
    out["atr14"] = atr(bars, 14)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    out["bollinger_mid"], out["bollinger_upper"], out["bollinger_lower"] = mid, mid + 2 * sd, mid - 2 * sd
    out["bollinger_width"] = 4 * sd / mid
    out["historical_volatility"] = np.log(c / c.shift()).rolling(20).std(ddof=1) * math.sqrt(252)
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    out["tenkan"], out["kijun"] = tenkan, kijun
    out["senkou_a"] = ((tenkan + kijun) / 2).shift(26)
    out["senkou_b"] = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    # Chikou is plotted 26 bars back; current decision compares to past close.
    out["chikou_value"] = c
    out["chikou_reference_close"] = c.shift(26)
    out["volume_ma20"] = v.rolling(20).mean()
    out["relative_volume"] = v / v.shift().rolling(20).mean().replace(0, np.nan)
    out["volume_acceleration"] = v / v.shift().replace(0, np.nan) - 1
    out["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
    flow = typical * v
    positive = flow.where(typical.diff() > 0, 0).rolling(14).sum()
    negative = flow.where(typical.diff() < 0, 0).rolling(14).sum()
    out["mfi14"] = 100 * positive / (positive + negative).replace(0, np.nan)
    out["support"] = l.shift().rolling(20).min()
    out["resistance"] = h.shift().rolling(20).max()
    out["recent_high"] = h.rolling(20).max()
    out["recent_low"] = l.rolling(20).min()
    # A pivot becomes known only two bars after it occurred.
    out["swing_high"] = h.shift(2).where(h.shift(2) == h.rolling(5).max()).ffill()
    out["swing_low"] = l.shift(2).where(l.shift(2) == l.rolling(5).min()).ffill()
    records: list[dict[str, Any]] = []
    for raw in out.to_dict("records"):
        item = {key: (str(value) if key == "date" else finite(value)) for key, value in raw.items()}
        a, b = item["senkou_a"], item["senkou_b"]
        item["cloud_direction"] = None if a is None or b is None else "bull" if a > b else "bear" if a < b else "neutral"
        item["price_cloud"] = None if a is None or b is None else "above" if item["close"] > max(a, b) else "below" if item["close"] < min(a, b) else "inside"
        item["breakout"] = None if item["resistance"] is None else item["close"] > item["resistance"]
        item["breakdown"] = None if item["support"] is None else item["close"] < item["support"]
        item["volume_breakout"] = None if item["relative_volume"] is None else item["relative_volume"] >= 1.5
        records.append(item)
    return records


def technical_score(latest: dict[str, Any]) -> dict[str, Any]:
    rules = [("EMA20 > EMA50", latest.get("ema20"), latest.get("ema50")),
             ("RSI14 > 50", latest.get("rsi14"), 50),
             ("MACD > signal", latest.get("macd"), latest.get("macd_signal")),
             ("close > SMA200", latest.get("close"), latest.get("sma200"))]
    positive, negative, neutral = [], [], []
    for label, left, right in rules:
        (neutral if left is None or right is None or left == right else positive if left > right else negative).append(label)
    complete = all(a is not None and b is not None for _, a, b in rules)
    return {"value": (100 * (len(positive) + .5 * len(neutral)) / len(rules)) if complete else None,
            "positive_factors": positive, "negative_factors": negative, "neutral_factors": neutral,
            "method": "equal-weight four causal technical comparisons; all required"}


def multi_timeframe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for timeframe in ("daily", "weekly", "monthly"):
        if timeframe == "daily":
            grouped = rows
        else:
            groups: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                stamp = pd.Timestamp(row["source_date"])
                key = str(stamp.to_period("W-FRI" if timeframe == "weekly" else "M"))
                groups.setdefault(key, []).append(row)
            grouped = []
            # Exclude newest incomplete period, even when its last bar is missing.
            for batch in list(groups.values())[:-1]:
                grouped.append({"date": batch[-1]["source_date"], "open": batch[0]["open"],
                                "close": batch[-1]["close"], "high": max(x["high"] for x in batch),
                                "low": min(x["low"] for x in batch), "volume": sum(x["volume"] for x in batch)})
        history = indicator_history(grouped)
        latest = history[-1] if history else {}
        output[timeframe] = {"status": "available" if len(history) >= 200 else "insufficient_data",
                             "bars": len(history), "latest": latest, "score": technical_score(latest),
                             "completed_periods_only": timeframe != "daily"}
    output["intraday"] = {"status": "unavailable", "reason": "No verified intraday series supplied"}
    return output
