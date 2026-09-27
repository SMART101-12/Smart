"""Stable report sections shared by service/API callers."""
from __future__ import annotations
from typing import Any


class AnalysisOutputFormatter:
    def format(self, analysis: dict[str, Any]) -> dict[str, Any]:
        support = analysis.get("decision_support", {})
        return {"schema_version": "smart-report-v1", "symbol": analysis.get("symbol"),
                "as_of": analysis.get("as_of"), "status": analysis.get("status"),
                "summary": {"action": support.get("action"), "reason": support.get("reason")},
                "data_quality": analysis.get("data_quality", {}),
                "technical_analysis": analysis.get("factor_engine", {}),
                "trade_plan": support.get("trade_plan"),
                "entry_exit": support.get("entry_exit", {}),
                "risk": {"invalidation_condition": (support.get("trade_plan") or {}).get("invalidation_condition")},
                "sources": analysis.get("lineage", {}),
                "warnings": [support["reason"]] if support.get("reason") else []}
