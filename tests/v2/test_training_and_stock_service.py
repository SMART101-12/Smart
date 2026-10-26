from datetime import date, timedelta

from smart_v2.ai.service import AIService
from smart_v2.ai.training import AITrainingService, TrainingConfig, build_training_dataset
from smart_v2.analysis.stock_service import StockAnalysisService


def _rows(count=100):
    rows = []
    price = 100.0
    start = date(2025, 1, 1)
    for index in range(count):
        price *= 1.001 if index % 4 else 0.999
        rows.append(
            {
                "dEven": (start + timedelta(days=index)).strftime("%Y%m%d"),
                "pFirst": price * 0.99,
                "pMax": price * 1.01,
                "pMin": price * 0.98,
                "pClosing": price,
                "pDrCotVal": price,
                "qTotTran5J": 1000 + index,
                "qTotCap": price * (1000 + index),
                "zTotTran": 10,
            }
        )
    return rows


def test_training_has_temporal_ranges_and_persists_memory(tmp_path):
    rows = _rows()
    dataset = build_training_dataset(rows, horizon=1, min_history=20)
    assert dataset[0]["decision_date"] < dataset[-1]["decision_date"]
    result = AITrainingService(memory_root=tmp_path).train(
        rows,
        symbol="TEST",
        config=TrainingConfig(min_history=20),
        run_id="run-1",
    )
    assert result["no_lookahead"] is True
    assert result["counts"]["train"] > 0
    assert result["artifact_path"].endswith("run-1.json")
    outcome = AIService(
        training_service=AITrainingService(memory_root=tmp_path)
    ).record_outcome(
        symbol="TEST",
        prediction_id="p1",
        decision_date=dataset[0]["decision_date"],
        horizon=1,
        realized_return=0.01,
    )
    assert outcome.endswith(".json")


def test_integrated_stock_service_returns_factor_and_lineage():
    result = StockAnalysisService().analyze(_rows(), symbol="TEST")
    assert result["status"] == "ANALYZED"
    assert 0 <= result["factor_engine"]["composite"] <= 100
    assert result["lineage"]["point_in_time"] is True
    assert result["decision_support"]["disclaimer"]


def test_non_trading_history_does_not_hide_verified_recent_levels():
    rows = _rows()
    missing = dict(rows[30], pFirst=0, pMax=0, pMin=0, qTotTran5J=0)
    rows[30] = missing
    report = StockAnalysisService().analyze(rows, symbol="TEST", include_history_metrics=False)
    quality = report["data_quality"]
    assert report["status"] == "ANALYZED"
    assert quality["status"] == "DEGRADED"
    assert quality["excluded_ohlcv_rows"] == 1
    assert quality["excluded_ohlcv_dates"] == ["2025-01-31"]
    assert missing["pMax"] == 0  # Source values are never overwritten or filled.
    assert report["decision_support"]["atr"] > 0
    assert report["decision_support"]["entry_exit"]["status"] == "no_setup"
    assert report["decision_support"]["conditional_levels"] is None
    assert report["decision_support"]["entry_exit"]["evidence"]["structural_levels"]


def test_unverified_latest_bar_cannot_issue_stale_entry_levels():
    rows = _rows()
    rows[-1] = dict(rows[-1], pFirst=0, pMax=0, pMin=0, qTotTran5J=0)
    report = StockAnalysisService().analyze(rows, symbol="TEST", include_history_metrics=False)
    assert report["data_quality"]["latest_bar_verified"] is False
    assert report["decision_support"]["entry_exit"]["status"] == "insufficient_data"
    assert report["decision_support"]["trade_plan"] is None
    assert report["decision_support"]["conditional_levels"] is None
