from copy import deepcopy

import pytest

from smart.final_decision import decide


def _bullish():
    return {"instrument_type": "EQUITY", "model_policy": {"approved": True}, "quality_gate": {
        "status": "MEDIUM", "freshness": "FRESH", "latest_bar_verified": True,
        "latest_valid_date": "2026-09-28", "corporate_action_adjustment": "VERIFIED", "blockers": []},
        "market": {"status": "SUCCESS", "regime": "BULL", "source_validation": "VERIFIED"},
        "industry": {"status": "SUCCESS", "regime": "BULL", "source_validation": "VERIFIED"},
        "technical_structure": {"score_0_100": 85},
        "fundamental": {"financial_score": 80},
        "fundamental_quality_gate": {"point_in_time": True, "blockers": []},
        "flow": {"observed_client_type": {"status": "SUCCESS", "signal": "BULLISH"},
                 "price_volume_proxy": {"signal": "BULLISH", "volume_ratio_20": 1.5}, "conflicts": []},
        "setup": {"state": "CONFIRMED", "confirmed_plan": {"entry": 100},
                  "reward_risk_1": 2.5, "risk": "LOW", "liquidity": "VERIFIED",
                  "gap_execution_risk": "VERIFIED"},
        "backtest": {"audit": {"validation_passed": True, "frozen_test_passed": True}},
        "self_test": {"decision": "PAPER_WATCH_CANDIDATE"}}


def test_complete_verified_evidence_is_required_for_buy():
    result = decide(_bullish())
    assert result["state"] == "BUY"
    assert result["failed_gates"] == []
    assert result["confidence"]["probability_of_profit"] is None
    assert result["confidence"]["calibrated"] is False


@pytest.mark.parametrize("case,expected", [
    ("setup_failed", "NO_SETUP"), ("negative_flow", "WATCH"),
    ("backtest_failed", "WAIT"), ("technical_mixed", "WATCH"),
    ("degraded_data", "WAIT"), ("missing_nav", "WATCH")])
def test_high_score_never_overrides_failed_gate(case, expected):
    summary = deepcopy(_bullish())
    if case == "setup_failed":
        summary["setup"]["state"] = "NO_SETUP"
    elif case == "negative_flow":
        summary["flow"]["observed_client_type"]["signal"] = "BEARISH"
        summary["flow"]["conflicts"] = ["outflow_against_trend"]
    elif case == "backtest_failed":
        summary["backtest"]["audit"]["validation_passed"] = False
        summary["self_test"]["decision"] = "REJECT"
    elif case == "technical_mixed":
        summary["technical_structure"]["score_0_100"] = 50
    elif case == "degraded_data":
        summary["quality_gate"]["status"] = "DEGRADED"
    else:
        summary["instrument_type"] = "FUND"
        summary["fundamental"] = {"net_asset_value_per_unit": None}
    result = decide(summary)
    assert result["state"] == expected
    assert result["failed_gates"]


def test_missing_evidence_does_not_silently_redistribute_weights():
    summary = _bullish()
    summary["market"] = {"status": "UNAVAILABLE", "regime": "UNKNOWN"}
    result = decide(summary)
    assert result["weighted_evidence_score"] is None
    assert result["evidence_scores"]["market"] is None
    assert result["evidence_coverage_weight_pct"] == 90


def test_current_quality_changes_are_versioned_and_other_entry_gates_still_apply():
    summary = _bullish()
    summary["quality_gate"].update(status="DEGRADED", current_window={"status": "MEDIUM"})
    assert decide(summary)["gates"]["data_quality"] is True
    assert decide(summary, version="DECISION-1.1")["gates"]["data_quality"] is False
    summary["model_policy"]["approved"] = False
    assert decide(summary)["state"] != "BUY"
    summary["quality_gate"]["current_window"]["status"] = "DEGRADED"
    assert decide(summary)["gates"]["data_quality"] is False
