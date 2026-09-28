"""Conditional setup lifecycle; a hypothetical level is never an order."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from .archive import parse_market_date


def assess_setup(levels: dict[str, Any] | None, *, gate: dict[str, Any] | None,
                 market: dict[str, Any] | None, industry: dict[str, Any] | None,
                 flow: dict[str, Any] | None, technical: dict[str, Any] | None,
                 model_decision: str | None, last_close: float | None = None) -> dict[str, Any]:
    levels, gate, market, industry, flow, technical = (v or {} for v in
                                                       (levels, gate, market, industry, flow, technical))
    candidate = levels.get("plan") or levels.get("conditional")
    source_day = ((levels.get("evidence") or {}).get("as_of") or
                  (candidate or {}).get("as_of"))
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
    atr = (levels.get("evidence") or {}).get("atr")
    risk_pct = round((entry - stop) / entry * 100, 3) if entry and stop and entry > stop > 0 else None
    reward1 = round((target1 - entry) / (entry - stop), 3) if risk_pct and target1 else None
    reward2 = round((target2 - entry) / (entry - stop), 3) if risk_pct and target2 else None
    atr_pct = round(atr / entry * 100, 3) if atr and entry else None
    risk = "EXTREME" if risk_pct is None else "HIGH" if risk_pct > 8 or (atr_pct and atr_pct > 8) else "MEDIUM" if risk_pct > 4 else "LOW"
    if levels.get("plan") and last_close is not None and stop and last_close <= stop:
        state = "INVALIDATED"
        blocks.append("last_close_below_stop")
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
        if levels.get("status") == "ready" and not blocks:
            state = "CONFIRMED"
        elif levels.get("status") == "ready":
            state = "WATCH"
        elif technical.get("timeframes", {}).get("daily", {}).get("trend") == "UP":
            state = "SETUP_FORMING"
        else:
            state = "WATCH"
    return {"state": state, "as_of": observed_day.isoformat(),
            "expires_on": (observed_day + timedelta(days=7)).isoformat(),
            "confirmed_plan": candidate if state == "CONFIRMED" else None,
            "hypothetical": candidate if state != "CONFIRMED" else None,
            "entry": entry, "stop": stop, "target_1": target1, "target_2": target2,
            "risk_pct": risk_pct, "reward_risk_1": reward1, "reward_risk_2": reward2,
            "atr_pct": atr_pct, "risk": risk,
            "liquidity": "UNVERIFIED", "gap_execution_risk": "UNVERIFIED",
            "blockers": sorted(set(blocks))}
