"""Versioned research assumptions shared by plans, sizing and exit reviews."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class TradePolicy:
    volume_confirmation: float = 1.2
    stop_atr_buffer: float = 1.0
    min_net_reward_risk: float = 2.0
    second_net_reward_risk: float = 3.0
    max_stop_distance_pct: float = 8.0
    round_trip_cost_pct: float = 0.35
    slippage_pct: float = 0.0
    entry_validity_days: int = 7
    time_exit_sessions: int = 10

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"Invalid trade policy: {key}")
        if not 1 <= self.volume_confirmation <= 10 or not 0 < self.stop_atr_buffer <= 10:
            raise ValueError("Volume confirmation and ATR buffer are out of range")
        if not 1 <= self.min_net_reward_risk < self.second_net_reward_risk <= 10:
            raise ValueError("Net reward/risk targets must be ordered between 1 and 10")
        if not 0 < self.max_stop_distance_pct <= 30:
            raise ValueError("Invalid maximum stop distance")
        if self.round_trip_cost_pct + self.slippage_pct >= 10:
            raise ValueError("Costs must be below 10 percent")
        for key, maximum in (("entry_validity_days", 30), ("time_exit_sessions", 250)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"Invalid integer trade policy: {key}")

    @property
    def cost_rate(self) -> float:
        return (self.round_trip_cost_pct + self.slippage_pct) / 100

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def exit_rules(self) -> dict[str, Any]:
        return {
            "version": "EXIT-RULES-1", "stop": "price_touch",
            "gap_below_stop": "first_observed_open_not_stop_price",
            "same_bar_stop_and_target": "stop_first_if_order_unknown",
            "target_1": "review_partial_exit; no assumed partial fill",
            "target_2": "exit_remaining_position",
            "time_exit_sessions": self.time_exit_sessions,
            "time_exit": "decision_at_close_for_next_available_session",
            "trailing_stop": "raise_to_entry_after_confirmed_tp1; effective_next_session_only",
            "execution": "unverified_until_actual_fill; queues_and_suspensions_may_prevent_exit",
            "cost_model": "configured_round_trip_and_slippage_on_entry_notional",
            "round_trip_cost_pct": self.round_trip_cost_pct,
            "slippage_pct": self.slippage_pct,
        }
