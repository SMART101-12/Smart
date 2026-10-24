"""Regression coverage for causal research and persistent setup invalidation."""
from datetime import date, timedelta
from typing import Any

import pytest

from smart.archive import normalize_daily_row
from smart.position_review import review_position
from smart.risk import bar_exit
from smart.setup_state import assess_setup
from smart.symbol_learning import _aggregate_timeframe, normalize_bars, walk_forward_entry_simulation
from smart.technical_structure import _aggregate
from tests.test_setup_state import _inputs


def _candle(day: str, *, low: float = 103.0) -> dict[str, Any]:
    return {"date": day, "open": 104.0, "high": 106.0, "low": low,
            "close": 104.5, "volume": 1000.0}


def test_unfinished_tail_is_open_and_completed_trades_survive_appended_history() -> None:
    rows = [{"date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
             "open": 100 + i * .1, "high": 100 + i * .1 + .05,
             "low": 100 + i * .1 - .05, "close": 100 + i * .1,
             "volume": 1000} for i in range(180)]
    full = walk_forward_entry_simulation(rows, config_id="balanced-r1-10")
    prefix = walk_forward_entry_simulation(rows[:80], config_id="balanced-r1-10")
    assert prefix["latest"]["status"] == "POSITION_OPEN"
    assert prefix["trades"]
    assert prefix["trades"] == [trade for trade in full["trades"] if trade["exit_index"] < 80]
    assert all(trade["exit_index"] == trade["planned_exit_index"] for trade in prefix["trades"])


def test_research_and_structure_use_same_completed_saturday_week() -> None:
    rows = [_candle(day) for day in ("2026-09-19", "2026-09-20", "2026-09-21",
                                    "2026-09-22", "2026-09-23", "2026-09-26")]
    bars, completed = _aggregate_timeframe(normalize_bars(rows), "weekly")
    canonical = [normalize_daily_row(row) for row in rows]
    structural = _aggregate(canonical, "weekly", date(2026, 9, 26))
    assert completed == [None, None, None, None, None, 0]
    assert len(structural) == 1 and structural[0]["period"] == "2026-09-19"
    assert bars[0].volume == structural[0]["volume"] == 5000
    assert bars[0].close == structural[0]["close"]


def test_prior_target_reached_at_open_precedes_later_low_without_fill_claim() -> None:
    assert bar_exit(125, 126, 90, 100, 95, 120) == (120, "take_profit")
    assert bar_exit(120, 126, 90, 100, 95, 120) == (120, "take_profit")
    # No established opening event: retain conservative intrabar ordering.
    assert bar_exit(125, 126, 90, 100, 95, 120, allow_gap=False) == (95, "ambiguous_bar_stop_first")
    assert bar_exit(100, 126, 90, 100, 95, 120) == (95, "ambiguous_bar_stop_first")
    review = review_position(entry_price=100, stop=95, tp1=110, tp2=120,
                             bar={"date": "2026-09-28", "open": 115,
                                  "high": 116, "low": 90, "close": 100},
                             as_of=date(2026, 9, 28), holding_sessions=2)
    assert review["action"] == "TP1_REVIEW"
    assert review["actual_fill"] is None and review["execution_verified"] is False


def test_post_signal_stop_touch_persists_despite_later_recovery_and_expiry() -> None:
    levels, kwargs = _inputs()
    levels["plan"]["as_of"] = "2026-09-27"
    levels["evidence"]["as_of"] = "2026-09-30"
    kwargs["gate"]["as_of"] = "2026-09-30"
    observations = [_candle("2026-09-27", low=90), _candle("2026-09-28", low=98),
                    _candle("2026-09-29"), _candle("2026-09-30")]
    result = assess_setup(levels, **kwargs, observed_bars=observations)
    assert result["state"] == "INVALIDATED" and result["confirmed_plan"] is None
    assert result["invalidated_on"] == "2026-09-28"
    assert "post_signal_stop_touched" in result["blockers"]
    kwargs["gate"]["as_of"] = "2026-10-05"
    assert assess_setup(levels, **kwargs, observed_bars=observations)["invalidated_on"] == "2026-09-28"


def test_signal_day_low_and_future_rows_cannot_invalidate_current_plan() -> None:
    levels, kwargs = _inputs()
    kwargs["gate"]["as_of"] = "2026-09-28"
    visible = [_candle("2026-09-27", low=90), _candle("2026-09-28")]
    future = [_candle("2026-09-29", low=90)]
    first = assess_setup(levels, **kwargs, observed_bars=visible)
    assert first["state"] == "CONFIRMED" and first["invalidated_on"] is None
    assert assess_setup(levels, **kwargs, observed_bars=visible + future) == first


@pytest.mark.parametrize("low", [None, 0, float("nan"), 110])
def test_invalid_post_signal_candle_cannot_confirm_or_invent_stop(low: float | None) -> None:
    levels, kwargs = _inputs()
    kwargs["gate"]["as_of"] = "2026-09-28"
    row = {**_candle("2026-09-28"), "low": low}
    result = assess_setup(levels, **kwargs, observed_bars=[row])
    assert result["state"] == "WATCH" and result["invalidated_on"] is None
    assert "post_signal_observation_incomplete" in result["blockers"]
