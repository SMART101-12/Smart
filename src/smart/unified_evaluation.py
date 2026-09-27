"""Summarize the existing long-only learner without selecting on frozen test data."""
from __future__ import annotations

from typing import Any

from .symbol_learning import normalize_bars


def _buy_and_hold(bars: list, interval: dict[str, int], cost_pct: float) -> dict[str, Any]:
    """One next-open entry in a fixed range, closed at its final daily close."""
    start, stop = interval["start_index"], interval["stop_index"]
    if start + 1 >= stop or stop > len(bars):
        return {"status": "INSUFFICIENT_DATA", "net_return_pct": None}
    entry = bars[start + 1].open
    exit_price = bars[stop - 1].close
    if entry <= 0 or exit_price <= 0:
        return {"status": "INSUFFICIENT_DATA", "net_return_pct": None}
    return {"status": "COMPLETE", "entry_date": bars[start + 1].date,
            "exit_date": bars[stop - 1].date,
            "net_return_pct": round((exit_price / entry - 1) * 100 - cost_pct, 6),
            "method": "one long position, next open to final close, round-trip cost"}


def evaluate_profile(profile: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if profile.get("status") != "COMPLETE":
        return {"status": "INSUFFICIENT_DATA", "reason": profile.get("status"),
                "backtest": None, "self_test": None}
    selected = profile["selected_model"]
    protocol = profile["protocol"]
    ranges = profile["ranges"]
    cost = float(protocol["transaction_cost_pct_round_trip"])
    bars = normalize_bars(rows)
    # The profile itself may cap history by years. Reproduce the identical
    # observations and verify the boundaries before calculating a baseline.
    first = profile["coverage"]["first_date"]
    bars = [bar for bar in bars if bar.date >= first]
    if len(bars) != profile["coverage"]["bars_used"] or bars[-1].date != profile["coverage"]["last_date"]:
        return {"status": "INSUFFICIENT_DATA", "reason": "profile history mismatch",
                "backtest": None, "self_test": None}
    baseline = {phase: _buy_and_hold(bars, ranges[phase], cost)
                for phase in ("validation", "test")}
    metrics = selected["range_metrics"]
    validation_gate = selected["validation_gate"]
    test_gate = selected["test_gate"]
    test_return = metrics["test"].get("cumulative_return_pct")
    baseline_return = baseline["test"].get("net_return_pct")
    validation_return = metrics["validation"].get("cumulative_return_pct")
    validation_baseline = baseline["validation"].get("net_return_pct")
    beats_validation_baseline = (validation_return is not None and validation_baseline is not None
                                 and float(validation_return) > float(validation_baseline))
    beats_baseline = (test_return is not None and baseline_return is not None
                      and float(test_return) > float(baseline_return))
    checks = {
        "validation_gate": bool(validation_gate["passed"]),
        "frozen_oos_gate": bool(test_gate["passed"]),
        "beats_validation_buy_and_hold_after_costs": beats_validation_baseline,
        "beats_frozen_buy_and_hold_after_costs": beats_baseline,
        "validation_only_selection": protocol["candidate_selection"] == "validation_only"
            and protocol["frozen_test_used_for_candidate_selection"] is False,
        "point_in_time_entries": protocol["no_lookahead"] is True
            and protocol["entry_time"] == "next_open",
    }
    insufficient_sample = (
        (metrics["validation"].get("trades") or 0) < validation_gate.get("thresholds", {}).get("minimum_trades", 5)
        or (metrics["test"].get("trades") or 0) < test_gate.get("thresholds", {}).get("minimum_trades", 5)
    )
    if insufficient_sample:
        decision = "HOLD"
    elif all(checks.values()):
        decision = "PAPER_WATCH_CANDIDATE"
    else:
        decision = "REJECT"
    diagnostics = profile.get("failure_diagnostics") or {}
    return {
        "status": "COMPLETE",
        "backtest": {
            "status": "COMPLETE", "method": "single-position long-only, next-open entry, after-cost NAV",
            "transaction_cost_pct_round_trip": cost,
            "selected_config": selected["config"], "ranges": ranges,
            "metrics": metrics, "baseline": baseline,
            "frozen_test_used_for_selection": False,
            "trade_count": len(profile["analysis_path"]["entries_and_outcomes"]),
        },
        "self_test": {
            "status": "COMPLETE", "decision": decision, "checks": checks,
            "validation_gate": validation_gate, "test_gate": test_gate,
            "failure_reasons": diagnostics.get("losses_by_reason", {}),
            "conflicting_components_on_losses": diagnostics.get("conflicting_components_on_losses", {}),
            "limits": ["unadjusted corporate actions not independently verified",
                       "OHLC cannot determine intraday stop/target ordering"],
        },
    }
