"""Chronological research metrics, validation ranking and promotion gates."""
from __future__ import annotations

import math
from statistics import mean
from typing import Any, Sequence


# Fixed evidence thresholds apply independently to validation and frozen test.
MIN_VALIDATION_TRADES = 5
MIN_TEST_TRADES = 5
MIN_PROFIT_FACTOR = 1.0
MAX_ACCEPTABLE_DRAWDOWN_PCT = -35.0


def _round(value: float | None, digits: int = 6) -> float | None:
    return round(float(value), digits) if value is not None and math.isfinite(value) else None


def _trade_metrics(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    returns = [float(item["net_return_pct"]) / 100.0 for item in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    equity, peak, maximum_drawdown = 1.0, 1.0, 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak:
            maximum_drawdown = min(maximum_drawdown, equity / peak - 1.0)
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (None if not wins else float("inf"))
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "flats": len(returns) - len(wins) - len(losses),
        "win_rate_pct": _round(len(wins) / len(returns) * 100.0, 4) if returns else None,
        "mean_net_return_pct": _round(mean(returns) * 100.0, 6) if returns else None,
        "cumulative_return_pct": _round((equity - 1.0) * 100.0, 6),
        "max_drawdown_pct": _round(maximum_drawdown * 100.0, 6),
        "profit_factor": _round(profit_factor, 6) if profit_factor is not None and math.isfinite(profit_factor) else ("infinite" if profit_factor else None),
        "expectancy_pct": _round(mean(returns) * 100.0, 6) if returns else None,
    }


def _trades_in_range(trades: Sequence[dict[str, Any]], start: int, stop: int) -> list[dict[str, Any]]:
    return [
        item for item in trades
        # A validation trade that closes in the frozen test period has no
        # known validation outcome and must not influence candidate selection.
        if start <= int(item.get("decision_index", -1)) < stop
        and int(item.get("exit_index", stop)) < stop
    ]


def _range_boundaries(bar_count: int, initial_history: int) -> dict[str, int]:
    start = max(10, min(int(initial_history), max(10, bar_count - 1)))
    decisions = max(0, bar_count - start - 1)
    train_end = min(bar_count - 1, start + max(1, int(decisions * 0.60)))
    validation_end = min(bar_count - 1, train_end + max(1, int(decisions * 0.20)))
    return {"start": start, "train_end": train_end, "validation_end": validation_end, "end": bar_count - 1}


def _candidate_score(metrics: dict[str, Any]) -> float:
    """Rank validation candidates without looking at frozen test results.

    This score only resolves the order among candidates. A separate fixed gate
    below decides whether the validation evidence is sufficient at all.
    """

    trades = int(metrics.get("trades") or 0)
    if trades < MIN_VALIDATION_TRADES:
        # Do not let one or two lucky entries outrank an evidence-backed model.
        return -100000.0 + trades
    cumulative = float(metrics.get("cumulative_return_pct") or 0.0)
    drawdown = abs(float(metrics.get("max_drawdown_pct") or 0.0))
    win_rate = float(metrics.get("win_rate_pct") or 0.0)
    factor_value = metrics.get("profit_factor")
    factor = 0.0 if factor_value in (None, "infinite") else min(3.0, float(factor_value))
    return cumulative - 0.75 * drawdown + 0.04 * win_rate + 1.5 * factor


def _robustness_gate(
    metrics: dict[str, Any],
    *,
    phase: str,
    minimum_trades: int,
) -> dict[str, Any]:
    """Return fixed, auditable after-cost quality checks for one data range."""

    trades = int(metrics.get("trades") or 0)
    cumulative_return = float(metrics.get("cumulative_return_pct") or 0.0)
    max_drawdown = float(metrics.get("max_drawdown_pct") or 0.0)
    raw_factor = metrics.get("profit_factor")
    profit_factor_ok = raw_factor == "infinite" or (
        isinstance(raw_factor, (int, float))
        and math.isfinite(float(raw_factor))
        and float(raw_factor) > MIN_PROFIT_FACTOR
    )
    checks = {
        "minimum_trade_count": trades >= minimum_trades,
        "positive_cumulative_return_after_costs": cumulative_return > 0.0,
        "profit_factor_above_one": profit_factor_ok,
        "controlled_max_drawdown": max_drawdown >= MAX_ACCEPTABLE_DRAWDOWN_PCT,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "phase": phase,
        "passed": not failed_checks,
        "thresholds": {
            "minimum_trades": minimum_trades,
            "minimum_profit_factor_exclusive": MIN_PROFIT_FACTOR,
            "minimum_cumulative_return_pct_exclusive": 0.0,
            "maximum_drawdown_pct": MAX_ACCEPTABLE_DRAWDOWN_PCT,
        },
        "observed": {
            "trades": trades,
            "cumulative_return_pct": _round(cumulative_return, 6),
            "profit_factor": raw_factor,
            "max_drawdown_pct": _round(max_drawdown, 6),
        },
        "checks": checks,
        "failed_checks": failed_checks,
    }


def _promotion(selected: dict[str, Any]) -> dict[str, Any]:
    """Permit paper monitoring only when validation and test pass fixed gates."""

    metrics = selected.get("range_metrics") or {}
    validation_gate = selected.get("validation_gate") or _robustness_gate(
        metrics.get("validation") or {},
        phase="validation",
        minimum_trades=MIN_VALIDATION_TRADES,
    )
    test_gate = selected.get("test_gate") or _robustness_gate(
        metrics.get("test") or {},
        phase="test",
        minimum_trades=MIN_TEST_TRADES,
    )
    if validation_gate["passed"] and test_gate["passed"]:
        return {
            "decision": "PAPER_WATCH_CANDIDATE",
            "reason": "Validation-selected candidate remained positive on the untouched test range; paper monitoring is still required.",
            "validation_gate": validation_gate,
            "test_gate": test_gate,
        }
    failed = []
    if not validation_gate["passed"]:
        failed.append("validation: " + ", ".join(validation_gate["failed_checks"]))
    if not test_gate["passed"]:
        failed.append("test: " + ", ".join(test_gate["failed_checks"]))
    return {
        "decision": "RESEARCH_ONLY",
        "reason": (
            "The candidate lacks sufficient after-cost evidence in a required chronological range "
            f"({'; '.join(failed)}); do not treat it as a trading instruction."
        ),
        "validation_gate": validation_gate,
        "test_gate": test_gate,
    }
