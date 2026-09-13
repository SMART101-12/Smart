import math
from datetime import date, timedelta
from pathlib import Path

from smart.symbol_learning import (
    INDICATORS,
    TIMEFRAMES,
    _promotion,
    build_symbol_profile,
    walk_forward_entry_simulation,
)
from smart_v2.ai.training import AITrainingService


def _rows(count: int = 900) -> list[dict]:
    rows = []
    start = date(2022, 1, 1)
    for index in range(count):
        close = 100 + index * 0.08 + 5 * math.sin(index / 11) + 2 * math.sin(index / 37)
        rows.append(
            {
                "dEven": (start + timedelta(days=index)).strftime("%Y%m%d"),
                "pFirst": close * (0.997 if index % 2 else 1.002),
                "pMax": close * 1.018,
                "pMin": close * 0.982,
                "pClosing": close,
                "qTotTran5J": 1000 + (index % 17) * 80,
            }
        )
    return rows


def test_symbol_profile_is_per_symbol_long_only_and_persisted(tmp_path):
    profile = build_symbol_profile(
        _rows(),
        symbol="نماد آزمایشی",
        initial_history=20,
        evaluation_window=30,
        output_root=tmp_path,
        persist=True,
    )

    assert profile["status"] == "COMPLETE"
    assert profile["protocol"]["long_only_entries"] is True
    assert profile["protocol"]["candidate_selection"] == "validation_only"
    assert profile["protocol"]["frozen_test_used_for_candidate_selection"] is False
    assert set(profile["coverage"]["timeframes"]) == set(TIMEFRAMES)
    assert set(profile["indicator_weights"]) == set(TIMEFRAMES)
    assert set(profile["indicator_weights"]["daily"]) == set(INDICATORS)
    assert profile["analysis_path"]["weight_updates"]
    assert all(item["direction"] == "LONG" for item in profile["analysis_path"]["entries_and_outcomes"])
    assert Path(profile["artifact_path"]).exists()
    assert Path(profile["latest_artifact_path"]).exists()
    assert profile["current_entry"]["long_only"] is True
    assert profile["walk_forward"]["bootstrap_history"]["bars"] == 20
    assert {item["phase"] for item in profile["walk_forward_segments"]} == {
        "train", "validation", "test"
    }
    assert all(item["decision_days"] <= 30 for item in profile["walk_forward_segments"])
    assert all(item["history_available_bars"] >= 20 for item in profile["walk_forward_segments"])
    assert "validation_gate" in profile["selected_model"]
    assert "test_gate" in profile["promotion"]
    assert profile["current_entry"]["paper_monitoring_eligible"] == (
        profile["promotion"]["decision"] == "PAPER_WATCH_CANDIDATE"
    )


def test_future_rows_cannot_change_truncated_entry_simulation():
    original = _rows(320)
    altered = [dict(row) for row in original]
    for row in altered[180:]:
        for key in ("pFirst", "pMax", "pMin", "pClosing"):
            row[key] = float(row[key]) * 8.0

    first = walk_forward_entry_simulation(
        original,
        symbol="TEST",
        config_id="balanced-r1-10",
        initial_history=20,
        max_bars=180,
    )
    second = walk_forward_entry_simulation(
        altered,
        symbol="TEST",
        config_id="balanced-r1-10",
        initial_history=20,
        max_bars=180,
    )

    assert first["no_lookahead"] is True
    assert first["trades"] == second["trades"]
    assert first["final_weights"] == second["final_weights"]


def test_ai_training_service_exposes_symbol_entry_profile(tmp_path):
    profile = AITrainingService(memory_root=tmp_path).train_symbol_entry_profile(
        _rows(260),
        symbol="AI_TEST",
        initial_history=20,
        evaluation_window=30,
    )

    assert profile["status"] == "COMPLETE"
    assert profile["ai_training"]["per_symbol"] is True
    assert Path(profile["artifact_path"]).exists()


def test_promotion_requires_validation_evidence_even_if_test_is_profitable():
    selected = {
        "range_metrics": {
            "validation": {
                "trades": 4,
                "cumulative_return_pct": -1.0,
                "profit_factor": 0.8,
                "max_drawdown_pct": -8.0,
            },
            "test": {
                "trades": 12,
                "cumulative_return_pct": 20.0,
                "profit_factor": 1.8,
                "max_drawdown_pct": -12.0,
            },
        }
    }

    promotion = _promotion(selected)

    assert promotion["decision"] == "RESEARCH_ONLY"
    assert promotion["validation_gate"]["passed"] is False
    assert promotion["test_gate"]["passed"] is True
