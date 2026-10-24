"""Causal research replay of the actual EntryExitEngine, not a proxy model.

This is a plan-level experiment, not a replay of all fundamental/market gates.
It never promotes a model or assumes that a historical queue was executable.
"""
from __future__ import annotations

from typing import Any

from .archive import deduplicate_rows
from .risk import bar_exit
from smart_v2.analysis.trade_plan import EntryExitEngine, TradePlan
from smart_v2.analysis.trade_policy import TradePolicy


def replay_entry_plans(rows: list[dict[str, Any]], *, symbol: str,
                       policy: TradePolicy | None = None) -> dict[str, Any]:
    policy = policy or TradePolicy()
    engine = EntryExitEngine(policy)
    bars, audit = deduplicate_rows(rows, symbol=symbol)
    result: dict[str, Any] = {"version": "ENTRY-REPLAY-1", "status": "INSUFFICIENT_DATA",
        "symbol": symbol, "policy": policy.as_dict(), "trades": [], "pending": None,
        "validates_full_smart_decision": False, "model_approved": False,
        "execution_verified": False, "protocol": {
            "signal": "completed_daily_bar", "entry": "next_observed_open_inside_zone",
            "tp1": "half_position_at_reference_level", "tp2": "remaining_half",
            "trailing": "breakeven_after_tp1_effective_next_bar",
            "time_exit": "next_observed_open_after_holding_limit",
            "same_bar_order": "stop_before_targets_unless_gap_open_known",
            "cost": "frozen_policy_cost_on_entry_notional_once",
            "omitted": ["full_smart_gates", "queue_fills", "corporate_action_validation", "portfolio_sizing"]}}
    if len(bars) < 23 or audit["invalid_rows"] or audit["duplicate_dates"]:
        return result
    # Strict causal input: don't compress invalid sessions into false adjacency.
    for b in bars:
        try:
            bar_exit(b["open"], b["high"], b["low"], b["close"], 1, 2)
            if b["volume"] is None or b["volume"] < 0:
                raise ValueError("Missing volume")
        except (ValueError, TypeError):
            return result
    pending: TradePlan | None = None
    active: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    rejected_entries = 0
    for i, candle in enumerate(bars):
        if active is None and pending is not None:
            if (candle["source_date"] <= pending.expires_on and
                    pending.entry_zone[0] <= candle["open"] <= pending.entry_zone[1]):
                active = {"signal_date": pending.as_of, "entry_date": candle["source_date"],
                          "entry": candle["open"], "stop": pending.sl, "tp1": pending.tp1,
                          "tp2": pending.tp2, "remaining": 1.0, "gross_return": 0.0,
                          "entry_index": i, "fills": [], "time_due": False}
            else:
                rejected_entries += 1
            pending = None
        if active:
            def fill(price: float, fraction: float, reason: str) -> None:
                active["gross_return"] += fraction * (price / active["entry"] - 1)
                active["remaining"] -= fraction
                active["fills"].append({"date": candle["source_date"], "price": price,
                                        "fraction": fraction, "reason": reason, "hypothetical": True})

            if active["time_due"]:
                fill(candle["open"], active["remaining"], "time_exit_next_open")
            else:
                target = active["tp1"] if active["remaining"] == 1 else active["tp2"]
                outcome = bar_exit(candle["open"], candle["high"], candle["low"], candle["close"],
                                   active["stop"], target)
                if outcome:
                    price, reason = outcome
                    if reason != "take_profit":
                        fill(price, active["remaining"], reason)
                    elif active["remaining"] == 1:
                        fill(price, .5, "tp1")
                        if candle["high"] >= active["tp2"]:
                            fill(active["tp2"], .5, "tp2")
                        # Applied after current-bar outcome, never retroactively.
                        active["stop"] = max(active["stop"], active["entry"])
                    else:
                        fill(price, active["remaining"], "tp2")
                active["time_due"] = i - active["entry_index"] + 1 >= policy.time_exit_sessions
            if active["remaining"] == 0:
                active.update(exit_date=candle["source_date"],
                              net_return_pct=100 * (active["gross_return"] - policy.cost_rate))
                trades.append(active)
                active = None
        if active is None and i >= 21:
            # Only rows already visible at this decision; entry never at same close.
            generated = engine.generate(bars[max(0, i - 59):i + 1], symbol)
            pending = generated.plan
    result.update(status="COMPLETE", trades=trades, open_position=active,
                  pending=pending.as_dict() if pending else None,
                  rejected_next_open_entries=rejected_entries,
                  metrics={"closed_trades": len(trades),
                           "mean_net_return_pct": sum(t["net_return_pct"] for t in trades) / len(trades) if trades else None},
                  range={"start": bars[0]["source_date"], "end": bars[-1]["source_date"]})
    return result
