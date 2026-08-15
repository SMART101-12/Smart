"""Risk and trade-plan primitives for decision support."""

from __future__ import annotations


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
