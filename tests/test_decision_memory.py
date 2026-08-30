from smart.decision_memory import DecisionMemory


def test_decision_memory_records_and_settles_result(tmp_path):
    memory = DecisionMemory(tmp_path)
    created = memory.record_decision(
        "TEST",
        {"as_of": "20200102", "prediction": "UP", "indicators": {"rsi14": 55}},
    )
    decision_id = created["decision_id"]
    rows = [
        {"dEven": "20200101", "pClosing": 100},
        {"dEven": "20200102", "pClosing": 100},
        {"dEven": "20200103", "pClosing": 101},
        {"dEven": "20200104", "pClosing": 102},
        {"dEven": "20200105", "pClosing": 103},
        {"dEven": "20200106", "pClosing": 105},
        {"dEven": "20200107", "pClosing": 106},
    ]
    settled = memory.settle_from_rows("TEST", decision_id, rows, horizon=5)
    assert settled["outcome"]["result"] == "WIN"
    assert abs(settled["outcome"]["realized_return"] - 0.06) < 1e-12
    assert settled["outcome"]["failure_analysis"]["actual_direction"] == "UP"
    assert settled["outcome_artifact_path"]


def test_decision_memory_classifies_losses_and_summarizes(tmp_path):
    memory = DecisionMemory(tmp_path)
    created = memory.record_decision(
        "TEST",
        {
            "as_of": "20200101",
            "prediction": "UP",
            "confidence": 0.8,
            "indicators": {"rsi14": 75, "macd": -1},
        },
    )
    memory.record_outcome("TEST", created["decision_id"], realized_return=-0.02)
    summary = memory.summary("TEST")
    assert summary["losses"] == 1
    assert summary["outcomes_by_reason"]["direction_error"] == 1
    assert summary["recent_decisions"][0]["outcome"]["result"] == "LOSS"
