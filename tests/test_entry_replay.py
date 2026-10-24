from smart.entry_replay import replay_entry_plans
from smart_v2.analysis.trade_plan import EntryExitEngine
from smart_v2.analysis.trade_policy import TradePolicy
from tests.v2.test_trade_plan_regression import bars


def test_replay_uses_actual_plan_next_open_and_partial_exit() -> None:
    history = bars()
    plan = EntryExitEngine().generate(history, "TEST").plan
    history.append(dict(date="2026-01-23", open=102, low=101, high=plan.tp1 + .1,
                        close=plan.tp1, volume=150))
    history.append(dict(date="2026-01-24", open=100, low=99, high=105, close=101, volume=150))
    result = replay_entry_plans(history, symbol="TEST")
    trade = result["trades"][0]
    assert trade["signal_date"] == "2026-01-22" and trade["entry_date"] == "2026-01-23"
    assert trade["fills"][0]["price"] == plan.tp1
    assert trade["fills"][0]["fraction"] == .5
    assert trade["fills"][1]["reason"] == "gap_through_stop"
    assert trade["fills"][1]["price"] == 100
    assert result["model_approved"] is False and result["validates_full_smart_decision"] is False
    later = history + [dict(history[-1], date="2026-01-25", high=999)]
    assert replay_entry_plans(later, symbol="TEST")["trades"][0] == trade


def test_no_chase_and_incomplete_history() -> None:
    history = bars()
    history.append(dict(date="2026-01-23", open=130, low=129, high=131, close=130, volume=150))
    result = replay_entry_plans(history, symbol="TEST")
    assert result["rejected_next_open_entries"] == 1 and result["trades"] == []
    history[-1]["low"] = 0
    assert replay_entry_plans(history, symbol="TEST")["status"] == "INSUFFICIENT_DATA"


def test_time_exit_executes_only_next_observed_open() -> None:
    history = bars()
    history.extend([dict(date="2026-01-23", open=102, low=101, high=103, close=102, volume=100),
                    dict(date="2026-01-24", open=104, low=103, high=105, close=104, volume=100)])
    result = replay_entry_plans(history, symbol="TEST", policy=TradePolicy(time_exit_sessions=1))
    assert result["trades"][0]["fills"][0]["date"] == "2026-01-24"
    assert result["trades"][0]["fills"][0]["price"] == 104
    assert result["trades"][0]["fills"][0]["reason"] == "time_exit_next_open"
