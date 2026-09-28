"""Auditable after-cost trade diagnostics over frozen profile ranges."""
from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Any


def _phase(trades: list[dict[str, Any]], start: int, stop: int) -> dict[str, Any]:
    # The closing bar must also be within the range; future outcomes never
    # become validation evidence.
    closed = [t for t in trades if start <= int(t.get("decision_index", -1)) < stop
              and int(t.get("exit_index", stop)) < stop and
              isinstance(t.get("net_return_pct"), (int, float))]
    returns = [float(t["net_return_pct"]) for t in closed]
    peak, equity, bottom, longest, current = 1., 1., 0., 0, 0
    recovery = None
    drawdown_start = None
    for index, value in enumerate(returns):
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
        equity *= 1 + value / 100
        if equity >= peak:
            if drawdown_start is not None:
                recovered = index - drawdown_start
                recovery = max(recovered, recovery or 0)
                drawdown_start = None
            peak = equity
        else:
            drawdown_start = index if drawdown_start is None else drawdown_start
            bottom = min(bottom, equity / peak - 1)
    wins = sum(v for v in returns if v > 0)
    losses = -sum(v for v in returns if v < 0)
    deviation = pstdev(returns) if len(returns) >= 10 else None
    downside = sqrt(mean(min(0, r) ** 2 for r in returns)) if len(returns) >= 10 else None
    failure_causes: dict[str, int] = {}
    ambiguous = 0
    for trade in closed:
        if trade.get("exit_reason") == "ambiguous_bar_stop_first":
            ambiguous += 1
        if float(trade["net_return_pct"]) < 0:
            reason = str(trade.get("failure_reason") or trade.get("exit_reason") or "unknown")
            failure_causes[reason] = failure_causes.get(reason, 0) + 1
    return {"trades": len(closed), "profit_factor": round(wins / losses, 4) if losses else
            "infinite" if wins else None,
            "expectancy_pct": round(mean(returns), 4) if returns else None,
            "max_drawdown_pct": round(bottom * 100, 4),
            "longest_loss_streak": longest, "recovery_trades": recovery,
            "sharpe_per_trade": round(mean(returns) / deviation, 4) if deviation else None,
            "sortino_per_trade": round(mean(returns) / downside, 4) if downside else None,
            "intraday_order_ambiguous": ambiguous,
            "failure_causes": failure_causes}


def audit_backtest(profile: dict[str, Any] | None,
                   evaluation: dict[str, Any] | None) -> dict[str, Any]:
    if not profile or not evaluation or evaluation.get("status") != "COMPLETE":
        return {"status": "UNAVAILABLE", "reason": "frozen_profile_unavailable"}
    path = profile.get("analysis_path") or {}
    trades = path.get("entries_and_outcomes") or []
    ranges = profile.get("ranges") or {}
    result = {p: _phase(trades, ranges[p]["start_index"], ranges[p]["stop_index"])
              for p in ("validation", "test")}
    checks = (evaluation.get("self_test") or {}).get("checks") or {}
    return {"status": "COMPLETE", "phases": result,
            "validation_passed": all(checks.get(k) is True for k in (
                "validation_gate", "beats_validation_buy_and_hold_after_costs",
                "validation_only_selection", "point_in_time_entries")),
            "frozen_test_passed": bool(checks.get("frozen_oos_gate")),
            "failed_checks": [k for k, passed in checks.items() if passed is not True],
            "cost_pct_round_trip": profile.get("protocol", {}).get("transaction_cost_pct_round_trip"),
            "slippage_pct": "UNVERIFIED", "intraday_policy": "stop_first_if_stop_and_target_hit",
            "metric_note": "Sharpe and Sortino are per trade, not annualized; fewer than 10 trades are unavailable"}
