"""Point-in-time backtesting for Stock DNA.

This intentionally uses a next-session entry after a signal and measures
forward returns at fixed horizons. It is a research engine, not an execution
engine.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from .stock_dna import normalize_history, point_in_time_analysis


HORIZONS = (1, 3, 5, 10, 20)


def backtest(rows: list[dict[str, Any]], min_score: float = 65.0) -> dict[str, Any]:
    rows = normalize_history(rows)
    trades: list[dict[str, Any]] = []
    by_strategy: dict[str, list[float]] = defaultdict(list)
    by_regime: dict[str, list[float]] = defaultdict(list)

    for i in range(len(rows)):
        analysis = point_in_time_analysis(rows, i)
        if analysis.get("status") != "ok" or analysis["smart_score"] < min_score:
            continue
        if i + max(HORIZONS) >= len(rows):
            continue

        entry = float(analysis["price"])
        future = {h: float(rows[i + h].get("pClosing")) for h in HORIZONS}
        returns = {h: round((future[h] / entry - 1.0) * 100.0, 4) for h in HORIZONS}
        trade = {
            "signal_date": rows[i].get("dEven"),
            "entry_date": rows[i + 1].get("dEven"),
            "entry_price": entry,
            "regime": analysis["regime"],
            "smart_score": analysis["smart_score"],
            "returns_pct": returns,
            "strategies": [s["strategy"] for s in analysis["strategy_signals"]],
        }
        trades.append(trade)
        for strategy in trade["strategies"]:
            by_strategy[strategy].append(returns[5])
        by_regime[trade["regime"]].append(returns[5])

    def stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"count": 0}
        wins = sum(v > 0 for v in values)
        return {
            "count": len(values),
            "win_rate_pct": round(wins / len(values) * 100, 2),
            "avg_return_5d_pct": round(mean(values), 4),
            "best_5d_pct": round(max(values), 4),
            "worst_5d_pct": round(min(values), 4),
        }

    return {
        "status": "ok",
        "signals": len(trades),
        "min_score": min_score,
        "horizons_days": list(HORIZONS),
        "overall_5d": stats([t["returns_pct"][5] for t in trades]),
        "by_strategy_5d": {k: stats(v) for k, v in sorted(by_strategy.items())},
        "by_regime_5d": {k: stats(v) for k, v in sorted(by_regime.items())},
        "trades": trades,
        "point_in_time": True,
        "entry_rule": "next trading session after signal",
    }
