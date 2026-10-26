"""Conditional setup lifecycle; a hypothetical level is never an order."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence
from math import isfinite
from .archive import normalize_daily_row, parse_market_date
from smart_v2.analysis.trade_policy import TradePolicy


def _post_signal_stop_touch(
    observations: Sequence[dict[str, Any]], *, signal_day: date,
    through: date, stop: float,
) -> tuple[date | None, bool]:
    """Inspect only dated sessions after the plan became known at the close."""
    touched: list[date] = []
    incomplete = False
    for raw in observations:
        candle = normalize_daily_row(raw)
        if candle is None:
            incomplete = True
            continue
        day = date.fromisoformat(candle["source_date"])
        if not signal_day < day <= through:
            continue
        values = [candle.get(key) for key in ("open", "high", "low", "close")]
        if (any(type(value) not in (int, float) or not isfinite(value) or value <= 0
                for value in values)
                or not candle["low"] <= min(candle["open"], candle["close"])
                <= max(candle["open"], candle["close"]) <= candle["high"]):
            incomplete = True
            continue
        if candle["low"] <= stop:
            touched.append(day)
    return min(touched, default=None), incomplete


def assess_setup(levels: dict[str, Any] | None, *, gate: dict[str, Any] | None,
                 market: dict[str, Any] | None, industry: dict[str, Any] | None,
                 flow: dict[str, Any] | None, technical: dict[str, Any] | None,
                 model_decision: str | None, last_close: float | None = None,
                 policy: TradePolicy | None = None,
                 observed_bars: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    policy = policy or TradePolicy()
    levels, gate, market, industry, flow, technical = (v or {} for v in
                                                       (levels, gate, market, industry, flow, technical))
    candidate = levels.get("plan") or levels.get("conditional")
    source_day = ((candidate or {}).get("as_of") or
                  (levels.get("evidence") or {}).get("as_of"))
    observed_day = parse_market_date(source_day)
    blocks = list(gate.get("blockers", []))
    if gate.get("freshness") != "FRESH":
        blocks.append("market_bar_not_fresh")
    if not candidate or not observed_day or blocks:
        return {"state": "NO_SETUP", "as_of": observed_day.isoformat() if observed_day else None,
                "expires_on": None, "confirmed_plan": None,
                "hypothetical": candidate, "blockers": sorted(set(blocks or ["no_verified_setup"])),
                "risk": "EXTREME" if blocks else "UNKNOWN"}
    entry = (candidate.get("entry") or
             (candidate.get("entry_zone_if_confirmed") or [None, None])[-1])
    stop = candidate.get("stop") or candidate.get("stop_if_entered")
    target1 = candidate.get("tp1") or candidate.get("target_1_if_entered")
    target2 = candidate.get("tp2") or candidate.get("target_2_if_entered")
    prices = (entry, stop, target1, target2)
    if (any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in prices)
            or not stop < entry < target1 < target2):
        return {"state": "NO_SETUP", "confirmed_plan": None, "hypothetical": candidate,
                "as_of": observed_day.isoformat(), "expires_on": None, "risk": "EXTREME",
                "blockers": ["invalid_plan_geometry"]}
    expiry = parse_market_date(candidate.get("expires_on")) or (observed_day + timedelta(days=policy.entry_validity_days))
    evaluation_day = parse_market_date(gate.get("as_of")) or observed_day
    touch_day, incomplete_observations = (None, False)
    if levels.get("plan") and observed_bars is not None:
        touch_day, incomplete_observations = _post_signal_stop_touch(
            observed_bars, signal_day=observed_day,
            through=min(evaluation_day, expiry), stop=stop)
    zone = candidate.get("entry_zone") or candidate.get("entry_zone_if_confirmed")
    cost = entry * policy.cost_rate
    net_rr = (target1 - entry - cost) / (entry - stop + cost)
    net_rr2 = (target2 - entry - cost) / (entry - stop + cost)
    atr = (levels.get("evidence") or {}).get("atr")
    risk_pct = round((entry - stop) / entry * 100, 3) if entry and stop and entry > stop > 0 else None
    reward1 = round((target1 - entry) / (entry - stop), 3) if risk_pct and target1 else None
    reward2 = round((target2 - entry) / (entry - stop), 3) if risk_pct and target2 else None
    atr_pct = round(atr / entry * 100, 3) if atr and entry else None
    risk = "EXTREME" if risk_pct is None else "HIGH" if risk_pct > 8 or (atr_pct and atr_pct > 8) else "MEDIUM" if risk_pct > 4 else "LOW"
    if evaluation_day < observed_day:
        state = "NO_SETUP"
        blocks.append("future_dated_plan")
    elif touch_day is not None:
        state = "INVALIDATED"
        blocks.append("post_signal_stop_touched")
    elif evaluation_day > expiry:
        state = "EXPIRED"
        blocks.append("entry_validity_expired")
    elif incomplete_observations:
        state = "WATCH"
        blocks.append("post_signal_observation_incomplete")
    elif last_close is None or type(last_close) not in (int, float) or not isfinite(last_close) or last_close <= 0:
        state = "WATCH"
        blocks.append("current_price_unavailable")
    elif levels.get("plan") and last_close <= stop:
        state = "INVALIDATED"
        blocks.append("last_close_below_stop")
    elif zone and last_close > zone[1]:
        state = "EXPIRED"
        blocks.append("price_above_entry_zone_do_not_chase")
    elif zone and last_close < zone[0]:
        state = "WATCH"
        blocks.append("price_below_entry_zone_reconfirmation_required")
    else:
        if market.get("regime") in {"BEAR", "RISK_OFF"}:
            blocks.append("adverse_broad_market")
        if market.get("status") != "SUCCESS":
            blocks.append("broad_market_unavailable")
        if industry.get("regime") == "BEAR":
            blocks.append("adverse_industry")
        if industry.get("status") != "SUCCESS":
            blocks.append("industry_unavailable")
        if flow.get("observed_client_type", {}).get("signal") != "BULLISH":
            blocks.append("individual_inflow_unconfirmed")
        if flow.get("conflicts"):
            blocks.append("flow_conflict")
        if model_decision != "PAPER_WATCH_CANDIDATE":
            blocks.append("model_not_validated")
        if risk == "EXTREME":
            blocks.append("invalid_stop_risk")
        if risk_pct > policy.max_stop_distance_pct:
            blocks.append("stop_distance_exceeds_policy")
        if net_rr + 1e-10 < policy.min_net_reward_risk:
            blocks.append("net_reward_risk_below_policy")
        if net_rr2 + 1e-10 < policy.second_net_reward_risk:
            blocks.append("second_net_reward_risk_below_policy")
        if levels.get("status") == "ready" and not blocks:
            state = "CONFIRMED"
        elif levels.get("status") == "ready":
            state = "WATCH"
        elif technical.get("timeframes", {}).get("daily", {}).get("trend") == "UP":
            state = "SETUP_FORMING"
        else:
            state = "WATCH"
    return {"state": state, "as_of": observed_day.isoformat(),
            "expires_on": expiry.isoformat(), "evaluated_on": evaluation_day.isoformat(),
            "invalidated_on": touch_day.isoformat() if touch_day else None,
            "confirmed_plan": candidate if state == "CONFIRMED" else None,
            "hypothetical": candidate if state != "CONFIRMED" else None,
            "entry": entry, "stop": stop, "target_1": target1, "target_2": target2,
            "risk_pct": risk_pct, "reward_risk_1": reward1, "reward_risk_2": reward2,
            "net_reward_risk_1": round(net_rr, 6), "net_reward_risk_2": round(net_rr2, 6),
            "exit_rules": policy.exit_rules(),
            "atr_pct": atr_pct, "risk": risk,
            "liquidity": "UNVERIFIED", "gap_execution_risk": "UNVERIFIED",
            "blockers": sorted(set(blocks))}
