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
    if "fails policy" in result["reason"] or "extended" in result["reason"]:
        return {**result, "signal_status": "NO_SETUP", "conditional": None}
    evidence = result["evidence"]
    resistance = evidence.get("resistance")
    atr = evidence.get("atr")
    if not isinstance(resistance, (int, float)) or not isinstance(atr, (int, float)) or atr <= 0:
        return {**result, "signal_status": "NO_SETUP", "conditional": None}
    trigger = resistance + .1 * atr
    upper = trigger + .25 * atr
    stop = resistance - engine.policy.stop_atr_buffer * atr
    plan = engine.build_plan(symbol, "1d", trigger, upper, stop, evidence["as_of"])
    if plan is None:
        return {**result, "signal_status": "NO_SETUP", "conditional": None}
    return {**result, "signal_status": "NO_SETUP", "conditional": {
        "kind": "hypothetical_breakout_only", "as_of": evidence.get("as_of"),
        "entry_zone_if_confirmed": [round(trigger, 6), round(upper, 6)],
        "stop_if_entered": round(stop, 6),
        "target_1_if_entered": plan.tp1,
        "target_2_if_entered": plan.tp2,
        "expires_on": plan.expires_on, "net_risk_reward": plan.net_risk_reward,
        "exit_rules": plan.exit_rules, "target_method": plan.target_method,
        "confirmation": f"daily close above trigger with volume at least {engine.policy.volume_confirmation:g} times the prior 20-bar average; reassess at next open",
        "invalidation": "no entry when the setup is unconfirmed or the model is rejected",
    }}
