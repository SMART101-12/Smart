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
