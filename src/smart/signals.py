"""Explainable signal components for SMART MVP."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SmartMoneySignal:
    phase: str
    score: float
    confirmations: tuple[str, ...]
    warnings: tuple[str, ...]


def smart_money_phase(
    *,
    price_change_pct: float,
    volume_ratio: float,
    money_flow_score: float,
    retail_buy_power: float,
) -> SmartMoneySignal:
    """Classify a phase using multiple confirmations, not one indicator."""
    score = 0.0
    confirmations: list[str] = []
    warnings: list[str] = []

    if volume_ratio >= 1.5:
        score += 25
        confirmations.append("abnormal_volume")
    if money_flow_score >= 60:
        score += 30
        confirmations.append("positive_money_flow")
    if retail_buy_power >= 1.5:
        score += 20
        confirmations.append("retail_buy_power")
    if price_change_pct > 0:
        score += 25
        confirmations.append("positive_price_response")

    if volume_ratio >= 2.0 and price_change_pct < 0:
        warnings.append("high_volume_with_negative_price")
    if money_flow_score < 40:
        warnings.append("weak_money_flow")

    if score >= 75 and len(confirmations) >= 3:
        phase = "accumulation_or_trend_initiation"
    elif score >= 45:
        phase = "watch"
    else:
        phase = "distribution_or_unconfirmed"

    return SmartMoneySignal(phase, round(score, 2), tuple(confirmations), tuple(warnings))
