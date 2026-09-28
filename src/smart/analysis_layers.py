"""Versioned layer boundary for the comprehensive analysis pipeline.

The first contract intentionally reports absent market/industry/decision
engines as unavailable. A completed calculation is not a positive signal.
Legacy top-level report fields remain readable during migration.
"""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "SMART-LAYERS-2.0"
LAYER_NAMES = ("data_quality", "market", "industry", "technical", "fundamental",
               "flow", "setup", "backtest", "risk", "decision")
STATUSES = frozenset({"SUCCESS", "PARTIAL", "FAILED", "UNAVAILABLE", "STALE", "INVALID"})
QUALITIES = frozenset({"HIGH", "MEDIUM", "LOW", "DEGRADED", "INVALID", "UNAVAILABLE"})


def layer(*, status: str, as_of: str | None, evidence: dict[str, Any] | None = None,
          errors: list[str] | None = None, data_quality: str = "UNAVAILABLE",
          provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    if status not in STATUSES or data_quality not in QUALITIES:
        raise ValueError("Unknown layer status or quality")
    if as_of is not None and not isinstance(as_of, str):
        raise ValueError("Layer as_of must be a source date string or absent")
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError("Layer evidence must be a mapping")
    if errors is not None and (not isinstance(errors, list) or
                               any(not isinstance(item, str) for item in errors)):
        raise ValueError("Layer errors must be strings")
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError("Layer provenance must be a mapping")
    return {"status": status, "evidence": evidence or {}, "errors": errors or [],
            "data_quality": data_quality, "as_of": as_of,
            "provenance": provenance or {}}


def from_legacy_summary(summary: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose honest layer states without changing historical report fields."""
    market_date = summary.get("as_of")
    quality = summary.get("data_quality") or {}
    gate = summary.get("quality_gate") or {}
    financial_quality = summary.get("fundamental_quality_gate") or {}
    fundamental = summary.get("fundamental") or {}
    flow = summary.get("smart_money") or {}
    independent_flow = summary.get("flow") or {}
    setup = summary.get("entry_exit") or {}
    setup_state = summary.get("setup") or {}
    backtest = summary.get("self_test") or {}
    audit = (summary.get("backtest") or {}).get("audit") or {}
    risk = summary.get("risk") or {}
    models = summary.get("market_models") or {}
    structure = summary.get("technical_structure") or {}
    warnings = summary.get("warnings") or []
    def errors(*names: str) -> list[str]:
        return [str(w.get("error")) for w in warnings
                if w.get("stage") in names and w.get("error")]
    def state(name: str) -> str:
        row = next((s for s in stages if s.get("name") == name), {})
        value = row.get("status")
        return "SUCCESS" if value == "COMPLETED" else "PARTIAL" if value == "PARTIAL" else "UNAVAILABLE"
    market_source = summary.get("provenance", {}).get("market")
    fundamental_source = summary.get("provenance", {}).get("fundamental")
    parts = {
        "data_quality": layer(status="INVALID" if gate.get("status") == "INVALID" else
                              "PARTIAL" if quality or gate else "UNAVAILABLE",
                              as_of=gate.get("latest_valid_date") or market_date,
                              evidence={"market_gate": gate, "existing_assessment": quality}
                              if quality or gate else {},
                              errors=list(gate.get("blockers", [])),
                              data_quality=gate.get("status", "DEGRADED" if quality else "UNAVAILABLE"),
                              provenance={"source": market_source} if market_source else {}),
        "market": _regime_layer(summary.get("market"), "broad_market_source_unavailable"),
        "industry": _regime_layer(summary.get("industry"), "industry_source_unavailable"),
        "technical": layer(status="SUCCESS" if structure.get("status") == "SUCCESS" else
                           "PARTIAL" if models.get("status") == "available" or structure.get("score_0_100") is not None else "UNAVAILABLE",
                           as_of=structure.get("as_of") or models.get("as_of"),
                           evidence={"daily_models": models.get("models", []),
                                     "price_structure": structure,
                                     "weekly_monthly_verified": all(
                                         (structure.get("timeframes") or {}).get(t, {}).get("status") == "SUCCESS"
                                         for t in ("weekly", "monthly"))} if models or structure else {},
                           data_quality="MEDIUM" if structure.get("status") == "SUCCESS" else
                           "DEGRADED" if models.get("status") == "available" else "UNAVAILABLE",
                           provenance={"source": market_source} if market_source else {}),
        "fundamental": layer(status="INVALID" if financial_quality.get("status") == "INVALID" else
                             state("fundamental") if fundamental else "UNAVAILABLE",
                             as_of=None, evidence={"source_gate": financial_quality,
                                                   "instrument_type": summary.get("instrument_type"),
                                                   "coverage": fundamental.get("coverage", {}),
                                                   "score": fundamental.get("financial_score")},
                             errors=errors("codal_sync", "fundamental_quality_gate", "fundamental")
                                    + financial_quality.get("blockers", []),
                             data_quality=financial_quality.get("status", "DEGRADED" if fundamental else "UNAVAILABLE"),
                             provenance={"source": fundamental_source} if fundamental_source else {}),
        "flow": layer(status="SUCCESS" if independent_flow.get("status") == "SUCCESS" else
                      "PARTIAL" if independent_flow.get("status") in {"PARTIAL", "CONFLICTING"} or flow else "UNAVAILABLE",
                      as_of=(independent_flow.get("observed_client_type") or {}).get("as_of") or market_date,
                      evidence={"analysis": independent_flow, "legacy_smart_money": flow},
                      errors=independent_flow.get("conflicts", []),
                      data_quality="MEDIUM" if independent_flow.get("status") == "SUCCESS" else
                      "DEGRADED" if independent_flow or flow else "UNAVAILABLE",
                      provenance={"source": market_source} if market_source else {}),
        "setup": layer(status="SUCCESS" if setup_state.get("state") == "CONFIRMED" else
                       "PARTIAL" if setup_state else "UNAVAILABLE",
                       as_of=setup_state.get("as_of"),
                       evidence={"lifecycle": setup_state,
                                 "status": setup.get("signal_status"),
                                 "reason": setup.get("reason"),
                                 "conditional": setup.get("conditional")},
                       errors=errors("entry_exit", "setup_state") + setup_state.get("blockers", []),
                       data_quality="DEGRADED" if setup else "UNAVAILABLE",
                       provenance={"source": market_source} if market_source else {}),
        "backtest": layer(status=state("model_self_test") if backtest else "UNAVAILABLE",
                          as_of=market_date,
                          evidence={"validation_decision": backtest.get("decision"),
                                    "audit": audit},
                          errors=errors("long_only_oos", "model_self_test"),
                          data_quality="DEGRADED" if backtest else "UNAVAILABLE",
                          provenance={"source": market_source} if market_source else {}),
        "risk": layer(status="PARTIAL" if risk else "UNAVAILABLE", as_of=market_date,
                      evidence={"existing_assessment": risk} if risk else {},
                      data_quality="DEGRADED" if risk else "UNAVAILABLE"),
        "decision": layer(status="SUCCESS" if summary.get("decision") else "UNAVAILABLE",
                          as_of=(summary.get("decision") or {}).get("as_of"),
                          evidence=summary.get("decision") or {},
                          errors=(summary.get("decision") or {}).get("failed_gates", []),
                          data_quality="MEDIUM" if summary.get("decision") else "UNAVAILABLE"),
    }
    assert tuple(parts) == LAYER_NAMES
    return {"contract_version": CONTRACT_VERSION, "layers": parts}


def _regime_layer(value: dict[str, Any] | None, fallback: str) -> dict[str, Any]:
    value = value or {}
    success = value.get("status") == "SUCCESS"
    return layer(status="SUCCESS" if success else "UNAVAILABLE",
                 as_of=value.get("as_of"), evidence=value.get("evidence") if success else {},
                 errors=value.get("errors") or ([] if success else [fallback]),
                 data_quality="MEDIUM" if success else "UNAVAILABLE",
                 provenance={"declared_source": value["source"],
                             "independently_authenticated": False} if value.get("source") else {})
