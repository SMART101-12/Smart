"""Versioned evidence aggregation with mandatory, independent entry gates."""
from __future__ import annotations

from math import isfinite
from typing import Any

VERSION = "DECISION-1.0"
WEIGHTS = {"market": 10, "industry": 10, "technical": 25,
           "fundamental": 15, "volume": 10, "money_flow": 15, "risk_reward": 15}


def _number(value: Any) -> float | None:
    return float(value) if type(value) in (int, float) and isfinite(value) else None


def decide(summary: dict[str, Any], *, weights: dict[str, int] | None = None) -> dict[str, Any]:
    weights = WEIGHTS.copy() if weights is None else weights.copy()
    if set(weights) != set(WEIGHTS) or any(type(w) is not int or w < 0 for w in weights.values()) or sum(weights.values()) != 100:
        raise ValueError("Decision weights must sum to 100 and match all evidence categories")
    market, industry, technical, fundamental, flow, setup, audit = (
        summary.get("market") or {}, summary.get("industry") or {},
        summary.get("technical_structure") or {}, summary.get("fundamental") or {},
        summary.get("flow") or {}, summary.get("setup") or {},
        (summary.get("backtest") or {}).get("audit") or {})
    gate = summary.get("quality_gate") or {}
    financial_gate = summary.get("fundamental_quality_gate") or {}
    observed_flow = flow.get("observed_client_type") or {}
    volume_proxy = flow.get("price_volume_proxy") or {}
    directional = {"BULL": 80., "BEAR": 20., "RISK_OFF": 0., "SIDEWAYS": 50., "NEUTRAL": 50.}
    flow_scores = {"BULLISH": 80., "BEARISH": 20., "NEUTRAL": 50.}
    fund = summary.get("instrument_type") == "FUND"
    rr = _number(setup.get("reward_risk_1"))
    evidence = {"market": directional.get(market.get("regime")),
                "industry": directional.get(industry.get("regime")),
                "technical": _number(technical.get("score_0_100")),
                "fundamental": _number(fundamental.get("valuation_score") if fund else fundamental.get("financial_score")),
                "volume": flow_scores.get(volume_proxy.get("signal")),
                "money_flow": flow_scores.get(observed_flow.get("signal")),
                "risk_reward": min(100., rr / 3 * 100) if rr is not None else None}
    contributions = {k: round(value * weights[k] / 100, 3)
                     for k, value in evidence.items() if value is not None}
    complete = all(v is not None or weights[k] == 0 for k, v in evidence.items())
    score = round(sum(contributions.values()), 3) if complete else None
    mandatory = {
        "data_quality": gate.get("status") in {"HIGH", "MEDIUM"} and
                        gate.get("freshness") == "FRESH" and gate.get("latest_bar_verified") is True and not gate.get("blockers"),
        "adjustment_history": gate.get("corporate_action_adjustment") == "VERIFIED",
        "market_context": market.get("status") == "SUCCESS" and market.get("regime") not in {"UNKNOWN", "BEAR", "RISK_OFF"},
        "industry_context": industry.get("status") == "SUCCESS" and industry.get("regime") not in {"UNKNOWN", "BEAR"},
        "context_source_verification": market.get("source_validation") == "VERIFIED"
                                      and industry.get("source_validation") == "VERIFIED",
        "technical_alignment": evidence["technical"] is not None and evidence["technical"] >= 60,
        "setup_confirmation": setup.get("state") == "CONFIRMED" and bool(setup.get("confirmed_plan")),
        "validation": audit.get("validation_passed") is True and audit.get("frozen_test_passed") is True
                      and (summary.get("self_test") or {}).get("decision") == "PAPER_WATCH_CANDIDATE",
        "individual_flow": observed_flow.get("status") == "SUCCESS" and observed_flow.get("signal") == "BULLISH"
                           and not flow.get("conflicts"),
        "volume_confirmation": _number(volume_proxy.get("volume_ratio_20")) is not None
                               and volume_proxy["volume_ratio_20"] >= 1.2,
        "financial_publication": financial_gate.get("point_in_time") is True and not financial_gate.get("blockers"),
        "fundamental_completeness": evidence["fundamental"] is not None,
        "risk_constraints": setup.get("risk") in {"LOW", "MEDIUM"} and rr is not None and rr >= 2
                            and setup.get("liquidity") == "VERIFIED" and setup.get("gap_execution_risk") == "VERIFIED",
        "complete_evidence": complete,
    }
    failed = [k for k, passed in mandatory.items() if not passed]
    if setup.get("state") == "INVALIDATED":
        state = "INVALIDATED"
    elif setup.get("state") == "NO_SETUP":
        state = "NO_SETUP"
    elif market.get("regime") in {"RISK_OFF", "BEAR"} or setup.get("risk") == "EXTREME":
        state = "AVOID"
    elif not failed and score is not None and score >= 65:
        state = "BUY"
    elif not mandatory["data_quality"] or not mandatory["validation"]:
        state = "WAIT"
    else:
        state = "WATCH"
    # This is a disclosed completeness assessment, never a forecast calibration.
    confidence_parts = {
        "source_quality": 20 if mandatory["data_quality"] else 0,
        "market_industry_clarity": 15 * (int(mandatory["market_context"]) + int(mandatory["industry_context"])) / 2,
        "signal_agreement": 15 if observed_flow.get("status") == "SUCCESS" and not flow.get("conflicts") else 0,
        "historical_validation": 20 if mandatory["validation"] else 0,
        "fundamental_completeness": 15 if mandatory["financial_publication"] and mandatory["fundamental_completeness"] else 0,
        "setup_completeness": 15 if mandatory["setup_confirmation"] else 0}
    return {"version": VERSION, "state": state, "as_of": gate.get("latest_valid_date"),
            "weights": weights, "evidence_scores": evidence,
            "observed_contributions": contributions, "weighted_evidence_score": score,
            "evidence_coverage_weight_pct": sum(weights[k] for k, v in evidence.items() if v is not None),
            "gates": mandatory, "failed_gates": failed,
            "reasons": failed or (["weighted_evidence_below_65"] if state != "BUY" else ["all_entry_gates_passed"]),
            "confidence": {"label": "Confidence in analytical evidence",
                           "score_0_100": sum(confidence_parts.values()), "components": confidence_parts,
                           "calibrated": False, "probability_of_profit": None}}
