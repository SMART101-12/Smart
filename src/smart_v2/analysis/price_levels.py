"""Confirmed price pivots with dated evidence; no percentage price projections."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _iso_day(day: str) -> str:
    return datetime.strptime(day, "%Y%m%d").date().isoformat()


def confirmed_price_levels(bars: list[tuple[str, dict[str, float]]]) -> dict[str, Any]:
    # Bound relevance to roughly one trading year, while allowing a pivot's
    # two left-hand observations to precede that window.
    groups: dict[tuple[str, float], dict[str, Any]] = {}
    for index in range(max(2, len(bars) - 250), len(bars) - 2):
        day, candle = bars[index]
        for kind, field in (("resistance", "high"), ("support", "low")):
            value = candle[field]
            left = [bars[i][1][field] for i in (index - 2, index - 1)]
            right = [bars[i][1][field] for i in (index + 1, index + 2)]
            pivot = (value > max(left) and value >= max(right) if field == "high"
                     else value < min(left) and value <= min(right))
            if not pivot:
                continue
            level = groups.setdefault((kind, value), {
                "kind": kind, "price": value, "pivot_dates": [],
                "confirmed_at": _iso_day(bars[index + 2][0]), "method": "two_left_two_right_pivot",
            })
            level["pivot_dates"].append(_iso_day(day))
            level["confirmed_at"] = _iso_day(bars[index + 2][0])
    close = bars[-1][1]["close"]
    return {
        "method": "confirmed_observed_pivots", "lookback_sessions": min(250, len(bars)),
        "as_of": _iso_day(bars[-1][0]),
        "supports": sorted((v for (k, price), v in groups.items()
                            if k == "support" and price < close), key=lambda v: -v["price"]),
        "resistances": sorted((v for (k, price), v in groups.items()
                               if k == "resistance" and price > close), key=lambda v: v["price"]),
    }
