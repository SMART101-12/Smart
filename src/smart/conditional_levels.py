"""Describe observed and conditional price levels without issuing an order."""
from __future__ import annotations

from typing import Any

from smart_v2.analysis.trade_plan import EntryExitEngine


def conditional_levels(history: list[dict[str, Any]], symbol: str,
                       *, model_decision: str | None) -> dict[str, Any]:
    valid = [row for row in history if all(isinstance(row.get(key), (int, float))
                                           and row[key] > 0 for key in ("open", "high", "low", "close"))
             and row["low"] <= min(row["open"], row["close"])
             <= max(row["open"], row["close"]) <= row["high"]]
    excluded = len(history) - len(valid)
    result = EntryExitEngine().generate(valid, symbol).as_dict()
    result["excluded_invalid_bars"] = excluded
    if result["status"] == "insufficient_data":
        return {**result, "signal_status": "NOT_AVAILABLE", "conditional": None}
    if result["plan"]:
        return {**result, "signal_status": "RESEARCH_ONLY" if model_decision != "PAPER_WATCH_CANDIDATE" else "CONDITIONAL_PAPER_WATCH",
                "conditional": result["plan"]}
    evidence = result["evidence"]
    resistance = evidence.get("resistance")
    atr = evidence.get("atr")
    if not isinstance(resistance, (int, float)) or not isinstance(atr, (int, float)) or atr <= 0:
        return {**result, "signal_status": "NO_SETUP", "conditional": None}
    trigger = resistance + .1 * atr
    upper = trigger + .25 * atr
    stop = resistance - atr
    if stop <= 0 or upper <= stop:
        return {**result, "signal_status": "NO_SETUP", "conditional": None}
    risk = upper - stop
    return {**result, "signal_status": "NO_SETUP", "conditional": {
        "kind": "hypothetical_breakout_only", "as_of": evidence.get("as_of"),
        "entry_zone_if_confirmed": [round(trigger, 6), round(upper, 6)],
        "stop_if_entered": round(stop, 6),
        "target_1_if_entered": round(upper + 2 * risk, 6),
        "target_2_if_entered": round(upper + 3 * risk, 6),
        "confirmation": "daily close above trigger with volume at least 1.2 times the prior 20-bar average; reassess at next open",
        "invalidation": "no entry when the setup is unconfirmed or the model is rejected",
    }}
