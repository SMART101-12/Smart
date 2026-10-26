"""Optional financial evidence must not discard a completed market analysis."""
from __future__ import annotations

from typing import Any

from .codal import HistoricalDataSyncManager
from .financial_history import HistoricalDataRepository
from .financial_scoring import FinancialScoringEngine, integrate_financial_score


def enrich_financial_history(row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Run blocking acquisition/scoring outside the request's event loop.

    Keep verified cached evidence when refresh fails. Never invent a financial
    score when the repository or scoring engine is unavailable.
    """
    symbol = row["symbol"]
    errors: list[dict[str, str]] = []
    financial: dict[str, Any] = {
        "symbol": symbol, "status": "SOURCE_UNAVAILABLE", "financial_score": None,
        "source": "KODAL", "warnings": [],
    }
    market_sync: dict[str, Any] = {}
    try:
        repository = HistoricalDataRepository()
        try:
            HistoricalDataSyncManager(repository).sync_financial(symbol)
        except Exception as exc:
            errors.append({"symbol": symbol, "stage": "financial_sync", "error": str(exc)})
        try:
            financial = FinancialScoringEngine(repository).analyze(symbol)
        except Exception as exc:
            errors.append({"symbol": symbol, "stage": "financial_scoring", "error": str(exc)})
        try:
            market_sync = repository.state(str(row.get("ins_code", "")), "TSETMC")
        except Exception as exc:
            errors.append({"symbol": symbol, "stage": "market_sync_state", "error": str(exc)})
    except Exception as exc:
        errors.append({"symbol": symbol, "stage": "financial_repository", "error": str(exc)})

    base_score = round(
        row["smart_money"]["score"] * 0.4 + row["technical"]["score"] * 0.35
        + row["data_quality"] * 0.25, 2,
    ) if row["smart_money"]["score"] is not None and row["technical"]["score"] is not None else None
    try:
        components = integrate_financial_score(base_score, financial)
    except Exception as exc:
        errors.append({"symbol": symbol, "stage": "financial_integration", "error": str(exc)})
        components = {"score": base_score, "base_score": base_score,
                      "financial_historical_score": financial.get("financial_score"),
                      "configured_weight": None, "applied_weight": 0}
    financial = {**financial, "warnings": [*financial.get("warnings", []), *(
        error["stage"] + ": " + error["error"] for error in errors)]}
    return {"financial_history": financial, "score_components": components,
            "overall_score": components["score"], "historical_market_sync": market_sync}, errors
