from datetime import date, timedelta

from smart.conditional_levels import conditional_levels
from smart_v2.analysis.trade_plan import EntryExitEngine


def range_breakout(with_resistances=True):
    start = date(2026, 1, 1)
    rows = [dict(date=str(start + timedelta(days=i)), open=99, high=101,
                 low=98, close=100, volume=100) for i in range(90)]
    if with_resistances:
        rows[5]["high"] = 140
        rows[11]["high"] = 125
    rows[-1].update(open=101, high=103, low=100, close=102, volume=160)
    return rows


def test_unconfirmed_range_never_fabricates_percentage_targets():
    rows = range_breakout()
    rows[-1].update(open=99, high=101, low=98, close=100, volume=100)
    result = conditional_levels(rows, "TEST", model_decision="REJECT")
    assert result["plan"] is None and result["conditional"] is None
    assert result["status"] == "no_setup"


def test_new_high_without_observed_overhead_never_gets_projected_targets():
    result = EntryExitEngine().generate(range_breakout(False), "TEST")
    assert result.status == "no_setup" and result.plan is None


def test_targets_are_observed_pivots_not_risk_multiples():
    result = EntryExitEngine().generate(range_breakout(), "TEST")
    assert result.plan is not None
    assert (result.plan.tp1, result.plan.tp2) == (125, 140)
    assert result.plan.target_method == "observed_pivot_resistance"
    assert result.plan.net_risk_reward[0] >= 2
    assert result.plan.net_risk_reward[1] >= 3
    evidence = result.plan.as_dict()["level_evidence"]
    assert evidence["target_1"]["pivot_dates"] == ["2026-01-12"]
    assert evidence["target_2"]["pivot_dates"] == ["2026-01-06"]


def test_second_target_must_pass_its_own_net_reward_requirement():
    assert EntryExitEngine().build_plan("TEST", "1d", 99, 100, 96,
                                       "20260331", [110, 111]) is None


def test_moving_entry_does_not_move_observed_exit_levels():
    rows = range_breakout()
    before = EntryExitEngine().generate(rows, "TEST").plan
    rows[-1].update(close=102.2, high=103.2)
    after = EntryExitEngine().generate(rows, "TEST").plan
    assert before is not None and after is not None
    assert before.entry_zone != after.entry_zone
    assert (before.tp1, before.tp2) == (after.tp1, after.tp2) == (125, 140)


def test_recent_unconfirmed_extreme_cannot_be_an_exit_target():
    rows = range_breakout(False)
    rows[-2]["high"] = 130
    result = EntryExitEngine().generate(rows, "TEST")
    assert result.plan is None


def test_nearest_observed_obstacle_cannot_be_skipped_to_force_reward_ratio():
    rows = range_breakout()
    rows[17]["high"] = 106
    result = EntryExitEngine().generate(rows, "TEST")
    assert result.plan is None


def test_setup_cannot_confirm_a_second_target_below_policy():
    from smart.setup_state import assess_setup
    from tests.test_setup_state import _inputs

    levels, kwargs = _inputs()
    levels["plan"]["tp2"] = 120
    result = assess_setup(levels, **kwargs)
    assert result["confirmed_plan"] is None
    assert "second_net_reward_risk_below_policy" in result["blockers"]


def test_stock_service_keeps_structural_evidence_older_than_sixty_bars():
    from smart_v2.analysis.stock_service import StockAnalysisService

    result = StockAnalysisService().analyze(range_breakout(), symbol="TEST", include_history_metrics=False)
    plan = result["decision_support"]["trade_plan"]
    assert plan is not None and (plan["tp1"], plan["tp2"]) == (125, 140)
