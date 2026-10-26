"""Describe observed and conditional price levels without issuing an order."""
from __future__ import annotations

from typing import Any
from math import isfinite
from .archive import normalize_daily_row

from smart_v2.analysis.trade_plan import EntryExitEngine
from smart_v2.analysis.trade_policy import TradePolicy


def conditional_levels(history: list[dict[str, Any]], symbol: str,
                       *, model_decision: str | None,
                       policy: TradePolicy | None = None) -> dict[str, Any]:
    engine = EntryExitEngine(policy)
    canonical = [normalize_daily_row(row, symbol=symbol) if isinstance(row, dict) else None
                 for row in history]
    valid = []
    excluded = []
    for raw, row in zip(history, canonical):
        if row is None:
            continue
        values = [row.get(k) for k in ("open", "high", "low", "close", "volume")]
        boolean_input = any(isinstance(v, bool) for k, v in raw.items()
                            if k in {"open", "high", "low", "close", "volume", "pFirst", "priceFirst",
                                     "pMax", "priceMax", "pMin", "priceMin", "pClosing", "qTotTran5J"})
        if (not boolean_input and all(type(v) in (int, float) and isfinite(v) for v in values)
                and row["volume"] >= 0 and 0 < row["low"] <= min(row["open"], row["close"])
                <= max(row["open"], row["close"]) <= row["high"]):
            valid.append(row)
        else:
            excluded.append(row["source_date"])
    latest = max((r["source_date"] for r in canonical if r), default=None)
    # Historical rejected observations remain auditable; never replace the
    # newest invalid candle with an older signal. Unknown/duplicate dates fail.
    invalid_dates = any(r is None for r in canonical)
    dates = [r["source_date"] for r in canonical if r]
    usable = not invalid_dates and len(dates) == len(set(dates)) and latest not in excluded
    result = engine.generate(valid if usable else [], symbol).as_dict()
    result["excluded_invalid_bars"] = len(excluded)
    result["excluded_invalid_dates"] = excluded
    result["latest_bar_verified"] = bool(usable and latest)
    if result["status"] == "insufficient_data":
        return {**result, "signal_status": "NOT_AVAILABLE", "conditional": None}
    if result["plan"]:
        return {**result, "signal_status": "RESEARCH_ONLY" if model_decision != "PAPER_WATCH_CANDIDATE" else "CONDITIONAL_PAPER_WATCH",
                "conditional": result["plan"]}
    return {**result, "signal_status": "NO_SETUP", "conditional": None}
