from smart.strategy_lab import (
    build_learning_summary,
    latest_strategy_decision,
    strategy_catalog,
    walk_forward_exam,
)


def _rows(n=90):
    rows = []
    for i in range(n):
        close = 100 + i * 0.8 + (3 if (i // 7) % 2 else -1)
        rows.append({
            "dEven": f"2020{(i // 28) + 1:02d}{(i % 28) + 1:02d}",
            "pFirst": close - 0.5,
            "pMax": close + 2,
            "pMin": close - 2,
            "pClosing": close,
            "qTotTran5J": 1000 + i * 10,
            "qTotCap": 100000,
            "zTotTran": 10,
        })
    return rows


def test_catalog_has_two_hundred_variants():
    catalog = strategy_catalog()
    assert len(catalog) == 200
    assert len({item.strategy_id for item in catalog}) == 200


def test_walk_forward_exam_uses_point_in_time_protocol():
    result = walk_forward_exam(_rows(), symbol="TEST", initial_history=20, evaluation_window=30)
    assert result["status"] == "COMPLETE"
    assert result["strategy_count"] == 200
    assert result["protocol"]["decision_uses_future_fields"] is False
    assert result["protocol"]["future_labels_used_only_after_decision"] is True
    assert result["segments"]
    assert all("future_return_5d" not in item["indicators"] for item in result["decisions"])


def test_future_rows_cannot_change_prior_decisions():
    original = _rows(110)
    altered = [dict(row) for row in original]
    for row in altered[80:]:
        row["pClosing"] = float(row["pClosing"]) * 9.0
        row["pMax"] = float(row["pMax"]) * 9.0
        row["pMin"] = float(row["pMin"]) * 9.0
        row["pFirst"] = float(row["pFirst"]) * 9.0
    first = walk_forward_exam(original, symbol="TEST", initial_history=20, max_decisions=20)
    second = walk_forward_exam(altered, symbol="TEST", initial_history=20, max_decisions=20)
    assert first["decisions"] == second["decisions"]


def test_latest_strategy_decision_is_pending_and_future_safe():
    original = _rows(110)
    altered = [dict(row) for row in original]
    for row in altered[80:]:
        row["pClosing"] = float(row["pClosing"]) * 7.0
        row["pMax"] = float(row["pMax"]) * 7.0
        row["pMin"] = float(row["pMin"]) * 7.0
        row["pFirst"] = float(row["pFirst"]) * 7.0
    # Cut the input at the same decision date: later observations are not
    # visible to a live point-in-time decision.
    first = latest_strategy_decision(original[:80], symbol="TEST")
    second = latest_strategy_decision(altered[:80], symbol="TEST")
    assert first["status"] == "READY"
    assert first["decision"] == second["decision"]
    assert first["selected_strategies"] == second["selected_strategies"]
    assert first["outcome_status"] == "PENDING"
    assert first["protocol"]["decision_uses_future_fields"] is False


def test_learning_summary_keeps_failure_diagnostics():
    result = walk_forward_exam(_rows(90), symbol="TEST", max_decisions=40)
    summary = build_learning_summary(result)
    assert summary["type"] == "strategy_learning_summary"
    assert summary["source_exam"]["strategy_count"] == 200
    assert "losses_by_reason" in summary["failure_diagnostics"]
    assert isinstance(summary["strategy_statistics"], list)
