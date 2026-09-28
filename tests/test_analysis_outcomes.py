from datetime import date, timedelta
import json

from smart.analysis_outcomes import learning_candidate, record_forward_outcomes, replay_decision
from smart.final_decision import decide


def _snapshot():
    summary = {"analysis_id": "a" * 32, "requested_symbol": "TEST",
               "quality_gate": {"latest_valid_date": "2026-09-01"},
               "technical_structure": {"timeframes": {"daily": {"last_close": 100}}}}
    summary["decision"] = decide(summary)
    return summary


def _rows():
    start = date(2026, 9, 1)
    return [{"date": (start + timedelta(days=i)).strftime("%Y%m%d"),
             "open": 100 + i, "close": 100 + i, "high": 101 + i,
             "low": 99 + i, "volume": 1000} for i in range(12)]


def test_outcomes_append_without_mutating_snapshot_or_leaking_future(tmp_path):
    summary = _snapshot()
    before = json.dumps(summary, sort_keys=True)
    first = record_forward_outcomes(summary, _rows(), tmp_path, as_of=date(2026, 9, 6))
    assert [r["horizon_sessions"] for r in first] == [1, 5]
    assert first[-1]["forward_close_return_pct"] == 5
    assert first[-1]["is_executed_trade_return"] is False
    paths = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    second = record_forward_outcomes(summary, _rows(), tmp_path, as_of=date(2026, 9, 12))
    assert [r["horizon_sessions"] for r in second] == [1, 5, 10]
    for name, contents in paths.items():
        assert (tmp_path / name).read_bytes() == contents
    assert json.dumps(summary, sort_keys=True) == before
    assert replay_decision(summary)["matches"] is True


def test_learning_is_research_only_and_revisions_do_not_inflate_sample():
    rows = [{"analysis_id": str(i), "horizon_sessions": 10,
             "forward_close_return_pct": 3} for i in range(30)]
    assert learning_candidate(rows[:20])["status"] == "INSUFFICIENT_DATA"
    candidate = learning_candidate(rows + rows)
    assert candidate["status"] == "RESEARCH_CANDIDATE"
    assert candidate["sample_count"] == 30
    assert candidate["production_active"] is False
