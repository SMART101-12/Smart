from datetime import date, timedelta

import pytest

from smart.technical_structure import analyze_technical_structure


def _history():
    first = date(2025, 1, 1)
    return [{"date": (first + timedelta(days=i)).strftime("%Y%m%d"),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000 + i} for i in range(370)]


def test_timeframes_exclude_incomplete_week_month_and_future_bars():
    rows = _history()
    cutoff = date(2026, 1, 2)
    before = analyze_technical_structure(rows, symbol="TEST", as_of=cutoff)
    changed = [dict(r) for r in rows]
    changed.append({"date": "20260103", "open": 2000, "high": 2100,
                    "low": 1900, "close": 2050, "volume": 50000})
    after = analyze_technical_structure(changed, symbol="TEST", as_of=cutoff)
    assert before["timeframes"]["weekly"] == after["timeframes"]["weekly"]
    assert before["timeframes"]["monthly"] == after["timeframes"]["monthly"]
    assert before["score_0_100"] == after["score_0_100"]
    assert before["score_is_trade_decision"] is False
    assert before["timeframes"]["weekly"]["last_completed"] < "2025-12-29"
    assert before["timeframes"]["monthly"]["last_completed"] < "2026-01-01"


def test_weights_are_explicit_and_validated():
    with pytest.raises(ValueError, match="weights"):
        analyze_technical_structure(_history(), symbol="TEST", as_of=date(2026, 1, 2),
                                    weights={"structure": 100})
