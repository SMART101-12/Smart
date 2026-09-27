"""Versioned layer boundary for the comprehensive analysis pipeline.

The first contract intentionally reports absent market/industry/decision
engines as unavailable. A completed calculation is not a positive signal.
Legacy top-level report fields remain readable during migration.
"""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "SMART-LAYERS-1.0"
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
    fundamental = summary.get("fundamental") or {}
    flow = summary.get("smart_money") or {}
    setup = summary.get("entry_exit") or {}
    backtest = summary.get("self_test") or {}
    risk = summary.get("risk") or {}
    models = summary.get("market_models") or {}
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
        "data_quality": layer(status="PARTIAL" if quality else "UNAVAILABLE",
                              as_of=market_date, evidence={"existing_assessment": quality,
                              "corporate_action_adjustment_verified": False} if quality else {},
                              data_quality="DEGRADED" if quality else "UNAVAILABLE",
                              provenance={"source": market_source} if market_source else {}),
        "market": layer(status="UNAVAILABLE", as_of=None,
                        errors=["Verified broad-market regime not integrated"]),
        "industry": layer(status="UNAVAILABLE", as_of=None,
                          errors=["Verified historical industry regime not integrated"]),
        "technical": layer(status="PARTIAL" if models.get("status") == "available" else "UNAVAILABLE",
                           as_of=models.get("as_of") if models else None,
                           evidence={"daily_models": models.get("models", []),
                                     "weekly_monthly_verified": False} if models else {},
                           data_quality="DEGRADED" if models.get("status") == "available" else "UNAVAILABLE",
                           provenance={"source": market_source} if market_source else {}),
        "fundamental": layer(status=state("fundamental") if fundamental else "UNAVAILABLE",
                             as_of=None, evidence={"instrument_type": summary.get("instrument_type"),
                                                   "coverage": fundamental.get("coverage", {}),
                                                   "score": fundamental.get("financial_score")},
                             errors=errors("codal_sync", "fundamental"),
                             data_quality="DEGRADED" if fundamental else "UNAVAILABLE",
                             provenance={"source": fundamental_source} if fundamental_source else {}),
        "flow": layer(status="PARTIAL" if flow else "UNAVAILABLE",
                      as_of=market_date, evidence={"smart_money_proxy": flow} if flow else {},
                      data_quality="DEGRADED" if flow else "UNAVAILABLE",
                      provenance={"source": market_source} if market_source else {}),
        "setup": layer(status=state("entry_exit") if setup else "UNAVAILABLE",
                       as_of=(setup.get("evidence") or {}).get("as_of"),
                       evidence={"status": setup.get("signal_status"),
                                 "reason": setup.get("reason"),
                                 "conditional": setup.get("conditional")},
                       errors=errors("entry_exit"),
                       data_quality="DEGRADED" if setup else "UNAVAILABLE",
                       provenance={"source": market_source} if market_source else {}),
        "backtest": layer(status=state("model_self_test") if backtest else "UNAVAILABLE",
                          as_of=market_date,
                          evidence={"validation_decision": backtest.get("decision")},
                          errors=errors("long_only_oos", "model_self_test"),
                          data_quality="DEGRADED" if backtest else "UNAVAILABLE",
                          provenance={"source": market_source} if market_source else {}),
        "risk": layer(status="PARTIAL" if risk else "UNAVAILABLE", as_of=market_date,
                      evidence={"existing_assessment": risk} if risk else {},
                      data_quality="DEGRADED" if risk else "UNAVAILABLE"),
        "decision": layer(status="UNAVAILABLE", as_of=None,
                          errors=["Hard-gate final decision is not integrated"]),
    }
    assert tuple(parts) == LAYER_NAMES
    return {"contract_version": CONTRACT_VERSION, "layers": parts}
