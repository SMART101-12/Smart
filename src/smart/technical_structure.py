"""Completed-period price structure and configurable, descriptive technical score."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from math import isfinite
from typing import Any

from .archive import deduplicate_rows

WEIGHTS = {"structure": 20, "trend": 15, "momentum": 15,
           "volume_flow": 20, "volatility": 10, "levels": 20}
VERSION = "TECH-STRUCTURE-2"


def _aggregate(rows: list[dict], period: str, cutoff: date) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        day = date.fromisoformat(row["source_date"])
        # The period containing cutoff might still have future sessions.
        if period == "weekly":
            # Tehran market week starts Saturday, not ISO Monday.
            start = day - timedelta(days=(day.weekday() - 5) % 7)
            current = cutoff - timedelta(days=(cutoff.weekday() - 5) % 7)
            key = start.isoformat()
            if start >= current:
                continue
        else:
            key = day.strftime("%Y-%m")
            if (day.year, day.month) >= (cutoff.year, cutoff.month):
                continue
        groups.setdefault(key, []).append(row)
    out = []
    for key, group in sorted(groups.items()):
        first, last = group[0], group[-1]
        out.append({"period": key, "last_date": last["source_date"],
                    "open": first["open"], "close": last["close"],
                    "high": max(r["high"] for r in group),
                    "low": min(r["low"] for r in group),
                    "volume": sum(r["volume"] for r in group),
                    "sessions": len(group)})
    return out


def analyze_technical_structure(history: list[dict[str, Any]], *, symbol: str,
                                as_of: date, weights: dict[str, int] | None = None) -> dict[str, Any]:
    weights = WEIGHTS.copy() if weights is None else weights.copy()
    if set(weights) != set(WEIGHTS) or any(type(v) is not int or v < 0 for v in weights.values()) or sum(weights.values()) != 100:
        raise ValueError("Technical category weights must be nonnegative integers totalling 100")
    canonical, audit = deduplicate_rows(history, symbol=symbol)
    valid = []
    for row in canonical:
        day = date.fromisoformat(row["source_date"])
        values = [row.get(k) for k in ("open", "high", "low", "close", "volume")]
        if (day <= as_of and all(type(v) in (int, float) and isfinite(v) and v > 0 for v in values)
                and row["low"] <= min(row["open"], row["close"])
                <= max(row["open"], row["close"]) <= row["high"]):
            valid.append(row)
    frames = {"daily": valid, "weekly": _aggregate(valid, "weekly", as_of),
              "monthly": _aggregate(valid, "monthly", as_of)}
    timeframes = {}
    for name, rows in frames.items():
        needed = {"daily": 22, "weekly": 8, "monthly": 6}[name]
        if len(rows) < needed:
            timeframes[name] = {"status": "UNAVAILABLE", "bars": len(rows),
                                "required": needed, "last_completed": rows[-1].get("last_date") if rows else None}
            continue
        latest, prior = rows[-1], rows[-2]
        recent = rows[-6:-1]
        upper, lower = max(r["high"] for r in recent), min(r["low"] for r in recent)
        breakout = "UP" if latest["close"] > upper else "DOWN" if latest["close"] < lower else "NONE"
        close = latest["close"]
        trend = ("UP" if close > mean(r["close"] for r in rows[-6:]) and close > prior["close"] else
                 "DOWN" if close < mean(r["close"] for r in rows[-6:]) and close < prior["close"] else "MIXED")
        timeframes[name] = {"status": "SUCCESS", "bars": len(rows),
                            "last_completed": latest.get("last_date") or latest["source_date"],
                            "trend": trend, "breakout": breakout,
                            "support": round(lower, 6), "resistance": round(upper, 6),
                            "pullback_to_support_pct": round(100 * (close / lower - 1), 3),
                            "last_close": close}
        if len(rows) >= 11:
            previous_window = rows[-11:-6]
            high_up = upper > max(r["high"] for r in previous_window)
            low_up = lower > min(r["low"] for r in previous_window)
            timeframes[name]["higher_high_and_low"] = high_up and low_up
            timeframes[name]["lower_high_and_low"] = (upper < max(r["high"] for r in previous_window)
                                                      and lower < min(r["low"] for r in previous_window))
        timeframes[name].update(
            failed_breakout_up=latest["high"] > upper and close <= upper,
            failed_breakout_down=latest["low"] < lower and close >= lower,
            gap_from_previous_close_pct=round(100 * (latest["open"] / prior["close"] - 1), 3),
            compression_ratio=round(mean(r["high"] - r["low"] for r in recent) /
                                    mean(r["high"] - r["low"] for r in rows[-needed:-1]), 3)
                                    if mean(r["high"] - r["low"] for r in rows[-needed:-1]) > 0 else None)
    daily = timeframes["daily"]
    score = None
    components = {}
    if daily["status"] == "SUCCESS":
        last = valid[-1]
        baseline = mean(r["volume"] for r in valid[-21:-1])
        ratio = last["volume"] / baseline if baseline > 0 else None
        tr = mean(r["high"] - r["low"] for r in valid[-14:])
        atr_pct = 100 * tr / last["close"]
        components = {"structure": .8 if daily["trend"] == "UP" else .2 if daily["trend"] == "DOWN" else .5,
                      "trend": .8 if timeframes["weekly"].get("trend") == "UP" else .2 if timeframes["weekly"].get("trend") == "DOWN" else .5,
                      "momentum": .8 if last["close"] > valid[-6]["close"] else .2 if last["close"] < valid[-6]["close"] else .5,
                      "volume_flow": .8 if ratio is not None and ratio >= 1.2 and last["close"] > valid[-2]["close"] else .2 if ratio is not None and ratio >= 1.2 and last["close"] < valid[-2]["close"] else .5,
                      "volatility": .2 if atr_pct > 8 else .5,
                      "levels": .8 if daily["breakout"] == "UP" else .2 if daily["breakout"] == "DOWN" else .5}
        score = round(sum(weights[k] * components[k] for k in weights), 2)
        daily["volume_ratio_20"] = round(ratio, 3) if ratio is not None else None
        daily["range_pct_14"] = round(atr_pct, 3)
    return {"status": "SUCCESS" if all(f["status"] == "SUCCESS" for f in timeframes.values()) else "PARTIAL" if score is not None else "UNAVAILABLE",
            "as_of": daily.get("last_completed"), "version": VERSION,
            "timeframes": timeframes, "weights": weights, "components": components,
            "score_0_100": score, "score_is_trade_decision": False,
            "excluded_rows": len(history) - len(valid), "duplicates": audit["duplicate_dates"]}
