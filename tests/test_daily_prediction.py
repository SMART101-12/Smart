from math import isclose

from smart.daily_prediction import normalize_rows, run_walk_forward


def _rows(n=80):
    rows = []
    price = 100.0
    for i in range(n):
        price *= 1.001 + (0.002 if i % 7 == 0 else 0)
        rows.append({"dEven": 20200000 + i + 1, "pClosing": price, "qTotTran5J": 1000 + i})
    return rows


def test_normalize_history_is_oldest_first_and_unique():
    rows = [
        {"dEven": 20200102, "pClosing": 101},
        {"dEven": 20200101, "pClosing": 100},
        {"dEven": 20200102, "pClosing": 102},
    ]
    out = normalize_rows(rows)
    assert [r["dEven"] for r in out] == [20200101, 20200102]
    assert out[-1]["pClosing"] == 102


def test_walk_forward_is_point_in_time_and_learns():
    report = run_walk_forward(_rows(), min_history=30)
    assert report["no_lookahead"] is True
    assert report["prediction_count"] == 49
    assert report["metrics"]["direction_accuracy_pct"] is not None
    assert isclose(sum(report["final_weights"].values()), 1.0, rel_tol=1e-12, abs_tol=1e-12)
    assert len(report["learning_log"]) == report["prediction_count"]
