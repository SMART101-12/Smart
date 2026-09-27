"""Opt-in real-source acceptance test; no synthetic data can satisfy this test."""
import os

import pytest

from smart.codal import HistoricalDataSyncManager
from smart.financial_history import HistoricalDataRepository
from smart.financial_scoring import FinancialScoringEngine


@pytest.mark.skipif(os.getenv("SMART_LIVE_CODAL") != "1",
                    reason="Requires reachable Codal; set SMART_LIVE_CODAL=1 explicitly")
def test_real_codal_five_year_source_coverage(tmp_path):
    symbol = os.getenv("SMART_LIVE_CODAL_SYMBOL", "فولاد")
    repo = HistoricalDataRepository(tmp_path / "real-codal.db")
    sync = HistoricalDataSyncManager(repo).sync_financial(symbol)
    assert sync["status"] == "SUCCESS", sync
    result = FinancialScoringEngine(repo).analyze(symbol)
    assert result["coverage"]["available"] >= 5, result
    for annual in result["annual"]:
        assert annual["cells"]["revenue"]["source_reference"]
        assert annual["cells"]["revenue"]["value"] is not None
