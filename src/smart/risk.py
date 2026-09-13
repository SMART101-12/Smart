"""Risk and trade-plan primitives for decision support.

The functions in this module are deliberately deterministic and side-effect
free. They provide guardrails for the UI/API layer without placing orders.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


def trade_plan(entry: float, stop: float, target: float) -> dict:
    if entry <= 0 or stop <= 0 or target <= 0:
        raise ValueError("prices must be positive")
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return {
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_per_unit": risk,
        "reward_per_unit": reward,
        "risk_reward": round(reward / risk, 2) if risk else None,
    }


def _finite_positive(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


def _finite_nonnegative(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite non-negative number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return result


def position_size(
    account_equity: float,
    risk_percent: float,
    entry: float,
    stop: float,
    target: float | None = None,
    *,
    max_allocation_percent: float = 25.0,
    fee_percent: float = 0.0,
    slippage_percent: float = 0.0,
) -> dict[str, Any]:
    """Calculate a long-only position size from a fixed account risk budget.

    Fees and slippage are charged on the entry notional and included in the
    per-unit risk. The result is advisory only; execution and lot rules remain
    the operator's responsibility.
    """

    equity = _finite_positive(account_equity, "account_equity")
    risk_pct = _finite_nonnegative(risk_percent, "risk_percent")
    entry_price = _finite_positive(entry, "entry")
    stop_price = _finite_positive(stop, "stop")
    if stop_price >= entry_price:
        raise ValueError("stop must be below entry for a long position")
    max_alloc = _finite_nonnegative(max_allocation_percent, "max_allocation_percent")
    fee = _finite_nonnegative(fee_percent, "fee_percent")
    slippage = _finite_nonnegative(slippage_percent, "slippage_percent")

    risk_budget = equity * risk_pct / 100.0
    cost_rate = (fee + slippage) / 100.0
    stop_distance = entry_price - stop_price
    risk_per_unit = stop_distance + entry_price * cost_rate
    units_by_risk = risk_budget / risk_per_unit
    units_by_allocation = equity * max_alloc / 100.0 / entry_price
    units = max(0.0, min(units_by_risk, units_by_allocation))
    notional = units * entry_price
    expected_loss = units * risk_per_unit
    result: dict[str, Any] = {
        "account_equity": round(equity, 8),
        "risk_percent": round(risk_pct, 8),
        "risk_budget": round(risk_budget, 8),
        "entry": round(entry_price, 8),
        "stop": round(stop_price, 8),
        "stop_distance": round(stop_distance, 8),
        "risk_per_unit": round(risk_per_unit, 8),
        "units": round(units, 8),
        "notional": round(notional, 8),
        "allocation_percent": round(notional / equity * 100.0, 8),
        "estimated_max_loss": round(expected_loss, 8),
        "capped_by_allocation": units_by_allocation < units_by_risk,
        "fee_percent": round(fee, 8),
        "slippage_percent": round(slippage, 8),
    }
    if target is not None:
        target_price = _finite_positive(target, "target")
        if target_price <= entry_price:
            raise ValueError("target must be above entry for a long position")
        reward = target_price - entry_price
        result.update({
            "target": round(target_price, 8),
            "reward_per_unit": round(reward, 8),
            "risk_reward": round(reward / risk_per_unit, 4),
            "estimated_gross_reward": round(units * reward, 8),
        })
    return result


def portfolio_summary(positions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize open positions and concentration without external state."""

    rows: list[dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0
    total_pnl = 0.0
    total_risk = 0.0
    for raw in positions:
        if not isinstance(raw, Mapping):
            continue
        symbol = str(raw.get("symbol") or "UNKNOWN").strip() or "UNKNOWN"
        quantity = _finite_positive(raw.get("quantity"), "quantity")
        entry_price = _finite_positive(raw.get("entry"), "entry")
        current_price = _finite_positive(raw.get("current", raw.get("price")), "current")
        cost = quantity * entry_price
        value = quantity * current_price
        pnl = value - cost
        stop = raw.get("stop")
        stop_risk = 0.0
        if stop is not None:
            stop_price = _finite_positive(stop, "stop")
            stop_risk = max(0.0, quantity * (current_price - stop_price))
        total_cost += cost
        total_value += value
        total_pnl += pnl
        total_risk += stop_risk
        rows.append({
            "symbol": symbol,
            "quantity": round(quantity, 8),
            "entry": round(entry_price, 8),
            "current": round(current_price, 8),
            "cost_basis": round(cost, 8),
            "market_value": round(value, 8),
            "unrealized_pnl": round(pnl, 8),
            "return_pct": round(pnl / cost * 100.0, 6),
            "stop_risk": round(stop_risk, 8),
        })
    for row in rows:
        row["allocation_percent"] = round(row["market_value"] / total_value * 100.0, 6) if total_value else 0.0
    return {
        "position_count": len(rows),
        "cost_basis": round(total_cost, 8),
        "market_value": round(total_value, 8),
        "unrealized_pnl": round(total_pnl, 8),
        "return_pct": round(total_pnl / total_cost * 100.0, 6) if total_cost else None,
        "stop_risk": round(total_risk, 8),
        "largest_allocation_percent": round(max((row["allocation_percent"] for row in rows), default=0.0), 6),
        "positions": rows,
    }
