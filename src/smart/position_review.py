"""Review an explicitly supplied open position, without creating orders or fills."""
from __future__ import annotations

from datetime import date
from typing import Any

from .archive import normalize_daily_row
from .risk import _finite_positive, bar_exit
from smart_v2.analysis.trade_policy import TradePolicy


def review_position(*, entry_price: float, stop: float, tp1: float, tp2: float,
                    bar: dict[str, Any], as_of: date, holding_sessions: int,
                    tp1_taken: bool = False, policy: TradePolicy | None = None) -> dict[str, Any]:
    """Position must already be open before this completed session began.

    The caller supplies actual entry and whether TP1 was actually executed.
    Merely touching TP1 does not manufacture a partial sale or alter the stop.
    ``stop`` is the stop active BEFORE this session; new stops apply next session.
    """
    policy = policy or TradePolicy()
    for key, value in (("entry", entry_price), ("stop", stop), ("tp1", tp1), ("tp2", tp2)):
        _finite_positive(value, key)
    if not entry_price < tp1 < tp2 or not stop < tp2:
        raise ValueError("Invalid long-position geometry")
    if type(holding_sessions) is not int or holding_sessions < 1 or type(tp1_taken) is not bool:
        raise ValueError("Explicit positive holding sessions and boolean TP1 state required")
    if not tp1_taken and stop >= tp1:
        raise ValueError("Active stop must be below the next target")
    candle = normalize_daily_row(bar)
    result: dict[str, Any] = {"version": "POSITION-REVIEW-1", "status": "insufficient_data",
                              "action": "REVIEW_DATA", "as_of": as_of.isoformat(),
                              "execution_verified": False, "actual_fill": None,
                              "exit_rules": policy.exit_rules()}
    if candle is None or candle["source_date"] != as_of.isoformat():
        return {**result, "reason": "A dated completed bar matching as_of is required"}
    try:
        outcome = bar_exit(candle["open"], candle["high"], candle["low"], candle["close"],
                           stop, tp2 if tp1_taken else tp1,
                           time_due=holding_sessions >= policy.time_exit_sessions)
    except (ValueError, TypeError):
        return {**result, "reason": "Incomplete or inconsistent price observation"}
    result.update(status="reviewed", action="HOLD", reason="No exit rule triggered",
                  active_stop=stop, next_session_stop=stop, reference_price=None,
                  source_row_hash=candle["source_row_hash"], holding_sessions=holding_sessions,
                  position_timing="position_open_before_observed_session")
    if outcome:
        price, reason = outcome
        action = "EXIT_REVIEW"
        if reason == "take_profit" and not tp1_taken:
            action = "TP1_REVIEW"
        if reason == "time_exit":
            action = "TIME_EXIT_REVIEW"
        result.update(action=action, reason=reason, reference_price=price,
                      reference_net_return_pct=100 * (price / entry_price - 1 - policy.cost_rate),
                      net_return_is_realized=False)
        if action == "TP1_REVIEW":
            result["stop_after_confirmed_tp1_next_session"] = max(stop, entry_price)
    # Never use this session's high to retroactively raise its stop.
    if tp1_taken and result["action"] == "HOLD":
        result["next_session_stop"] = max(stop, entry_price)
    result["warning"] = "Reference levels only; daily OHLC cannot prove fills or exit availability in queues"
    return result
