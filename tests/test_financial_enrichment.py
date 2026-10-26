import asyncio

import pytest

from smart import financial_enrichment as enrichment
from smart import tsetmc


def market_row(symbol):
    return {"symbol": symbol, "ins_code": symbol, "smart_money": {"score": 60},
            "technical": {"score": 80}, "data_quality": 100}


@pytest.mark.parametrize("failed_stage", ["repository", "sync", "scoring", "state", "integration"])
def test_financial_failure_preserves_market_and_other_symbols(monkeypatch, failed_stage):
    class Repository:
        def __init__(self):
            if failed_stage == "repository":
                raise OSError("database unavailable")

        def state(self, *_):
            if failed_stage == "state":
                raise OSError("state unavailable")
            return {"status": "SUCCESS"}

    def sync(self, symbol):
        if symbol == "BAD" and failed_stage == "sync":
            raise RuntimeError("source offline")

    def score(self, symbol):
        if symbol == "BAD" and failed_stage == "scoring":
            raise ValueError("invalid report")
        return {"financial_score": 90, "status": "VERIFIED", "warnings": []}

    def integrate(base, financial):
        if failed_stage == "integration":
            raise ValueError("invalid configuration")
        return {"score": base, "applied_weight": 0}

    async def analyze(symbol):
        return market_row(symbol)

    monkeypatch.setattr(enrichment, "HistoricalDataRepository", Repository)
    monkeypatch.setattr(enrichment.HistoricalDataSyncManager, "sync_financial", sync)
    monkeypatch.setattr(enrichment.FinancialScoringEngine, "analyze", score)
    monkeypatch.setattr(enrichment, "integrate_financial_score", integrate)
    monkeypatch.setattr(tsetmc, "analyze_symbol", analyze)
    result = asyncio.run(tsetmc.live_initial_analysis(["BAD", "GOOD"]))
    assert {row["symbol"] for row in result["results"]} == {"BAD", "GOOD"}
    assert all(row["overall_score"] == 77 for row in result["results"])
    assert any(error["symbol"] == "BAD" for error in result["errors"])
    bad = next(row for row in result["results"] if row["symbol"] == "BAD")
    assert bad["technical"] == {"score": 80}
    if failed_stage == "sync":
        assert bad["financial_history"]["financial_score"] == 90
        assert bad["financial_history"]["warnings"]
    if failed_stage in {"repository", "scoring"}:
        assert bad["financial_history"]["financial_score"] is None
