from datetime import date, timedelta
import json

import pytest
from fastapi.testclient import TestClient

from smart.conditional_levels import conditional_levels
from smart.position_review import review_position
from smart.risk import bar_exit, position_size
from smart.setup_state import assess_setup
from smart_v2.analysis.trade_plan import EntryExitEngine
from smart_v2.analysis.trade_policy import TradePolicy
from tests.test_setup_state import _inputs
from tests.test_final_decision import _bullish
from tests.v2.test_trade_plan_regression import bars


def test_plan_expiry_and_no_chasing() -> None:
    levels, kwargs = _inputs()
    kwargs["gate"]["as_of"] = "2026-10-05"
    result = assess_setup(levels, **kwargs)
    assert result["state"] == "EXPIRED" and result["confirmed_plan"] is None
    kwargs["gate"]["as_of"] = "2026-09-28"
    kwargs["last_close"] = 108
    result = assess_setup(levels, **kwargs)
    assert result["state"] == "EXPIRED"
    assert "price_above_entry_zone_do_not_chase" in result["blockers"]
    kwargs["last_close"] = 103
    assert assess_setup(levels, **kwargs)["state"] == "WATCH"


@pytest.mark.parametrize("bad", [None, float("nan"), True, -1])
def test_current_price_must_be_observed(bad: float | None) -> None:
    levels, kwargs = _inputs()
    kwargs["last_close"] = bad
    assert assess_setup(levels, **kwargs)["confirmed_plan"] is None


def test_overhead_resistance_rejects_insufficient_net_reward() -> None:
    engine = EntryExitEngine()
    assert engine.build_plan("TEST", "1d", 99, 100, 96, "20260927", [105, 140]) is None
    plan = engine.build_plan("TEST", "1d", 99, 100, 96, "20260927", [120, 140])
    assert plan and plan.tp1 <= 120 and plan.tp2 <= 140
    assert (plan.tp1, plan.tp2) == (120, 140)
    assert plan.net_risk_reward[0] >= 2 and plan.net_risk_reward[1] >= 3
    assert plan.expires_on == "2026-10-04"
    assert plan.overhead_resistances == (120, 140)
    assert engine.build_plan("TEST", "1d", 99, 100, 80, "20260927") is None


def test_invalid_latest_bar_is_not_silently_removed() -> None:
    history = bars()
    history.append({**history[-1], "date": "2026-01-23", "low": 0})
    result = conditional_levels(history, "TEST", model_decision="PAPER_WATCH_CANDIDATE")
    assert result["status"] == "insufficient_data" and result["conditional"] is None


def test_plan_causality_and_determinism() -> None:
    history = bars()
    before = EntryExitEngine().generate(history, "TEST").as_dict()
    with_future = history + [{**history[-1], "date": "2026-01-23", "volume": 999999}]
    after = EntryExitEngine().generate(with_future[:-1], "TEST").as_dict()
    assert before == after
    json.dumps(before, allow_nan=False)


def test_trend_pullback_requires_trend_reclaim_and_volume() -> None:
    rows = [{"date": str(date(2026, 1, 1) + timedelta(days=i)),
             "open": 100 + i * .1 - .05, "high": 100 + i * .1 + .1,
             "low": 100 + i * .1 - .1, "close": 100 + i * .1, "volume": 100.}
            for i in range(60)]
    rows[-2].update(open=105.05, high=105.35, low=104.85, close=105.15)
    rows[-1].update(open=105.15, low=105.05, high=105.85, close=105.65, volume=150)
    rows[5]["high"], rows[11]["high"] = 115, 130
    rows[-5]["low"] = 104.7
    result = EntryExitEngine().generate(rows, "TEST")
    assert result.status == "ready" and result.evidence["setup"] == "trend_pullback"
    assert (result.plan.tp1, result.plan.tp2) == (115, 130)
    assert result.plan.net_risk_reward[0] >= 2
    rows[-1]["volume"] = 100
    assert EntryExitEngine().generate(rows, "TEST").status == "no_setup"


@pytest.mark.parametrize("kwargs", [{"round_trip_cost_pct": float("nan")},
    {"entry_validity_days": True}, {"min_net_reward_risk": 4},
    {"time_exit_sessions": 0}, {"stop_atr_buffer": 0}])
def test_invalid_policy_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        TradePolicy(**kwargs)


def _review(**kwargs: object) -> dict:
    defaults = dict(entry_price=100, stop=95, tp1=110, tp2=120,
                    bar={"date": "2026-09-28", "open": 101, "high": 108, "low": 99, "close": 105},
                    as_of=date(2026, 9, 28), holding_sessions=2)
    defaults.update(kwargs)
    return review_position(**defaults)


def test_exit_stop_gap_and_ambiguous_bar_are_conservative() -> None:
    assert bar_exit(90, 122, 88, 100, 95, 120) == (90, "gap_through_stop")
    assert bar_exit(100, 122, 90, 110, 95, 120) == (95, "ambiguous_bar_stop_first")
    result = _review(bar={"date": "2026-09-28", "open": 90, "high": 111, "low": 88, "close": 99})
    assert result["reference_price"] == 90 and result["actual_fill"] is None
    assert result["execution_verified"] is False
    assert result["reference_net_return_pct"] == pytest.approx(-10.35)


def test_target_touch_does_not_invent_partial_sale_or_retroactive_stop() -> None:
    result = _review(bar={"date": "2026-09-28", "open": 101, "high": 112, "low": 99, "close": 108})
    assert result["action"] == "TP1_REVIEW"
    assert result["active_stop"] == result["next_session_stop"] == 95
    assert result["stop_after_confirmed_tp1_next_session"] == 100
    raised = _review(tp1_taken=True)
    assert raised["action"] == "HOLD" and raised["next_session_stop"] == 100
    assert raised["active_stop"] == 95


def test_time_exit_and_stale_bar() -> None:
    assert _review(holding_sessions=10)["action"] == "TIME_EXIT_REVIEW"
    assert _review(as_of=date(2026, 9, 29))["status"] == "insufficient_data"
    assert _review(bar={"date": "2026-09-28", "close": 105})["status"] == "insufficient_data"


def test_lot_sizing_and_limits() -> None:
    result = position_size(1000, 1, 103, 100, lot_size=2)
    assert result["units"] == 2 and result["estimated_max_loss"] <= result["risk_budget"]
    assert result["notional"] <= 250
    assert position_size(10, 1, 103, 100)["executable_size"] is False
    for kwargs in ({"risk_percent": 101}, {"max_allocation_percent": 101}, {"lot_size": True}):
        with pytest.raises(ValueError):
            position_size(**{**dict(account_equity=1000, risk_percent=1, entry=100, stop=90), **kwargs})


def test_new_gates_and_old_decision_replay() -> None:
    from smart.final_decision import decide
    summary = _bullish()
    summary["setup"]["net_reward_risk_1"] = 1.9
    assert decide(summary)["state"] != "BUY"
    assert decide(summary, version="DECISION-1.2")["state"] == "BUY"
    summary["setup"].update(net_reward_risk_1=2.1, state="EXPIRED")
    assert decide(summary)["state"] == "EXPIRED"


def test_exit_review_api() -> None:
    from smart.webapp import app
    payload = dict(entry_price=100, stop=95, tp1=110, tp2=120, holding_sessions=10,
                   as_of="2026-09-28", bar={"date": "2026-09-28", "open": 101, "high": 108, "low": 99, "close": 105})
    response = TestClient(app).post("/api/risk/review-position", json=payload)
    assert response.status_code == 200 and response.json()["action"] == "TIME_EXIT_REVIEW"
    assert TestClient(app).post("/api/risk/review-position", json={**payload, "stop": 130}).status_code == 422
