from smart.backtest_audit import audit_backtest


def test_validation_excludes_trade_closed_in_frozen_test_and_counts_ambiguity():
    profile = {"ranges": {"validation": {"start_index": 10, "stop_index": 20},
                          "test": {"start_index": 20, "stop_index": 30}},
               "protocol": {"transaction_cost_pct_round_trip": .35},
               "analysis_path": {"entries_and_outcomes": [
                   {"decision_index": 12, "exit_index": 18, "net_return_pct": -2,
                    "exit_reason": "ambiguous_bar_stop_first", "failure_reason": "stop_loss"},
                   {"decision_index": 19, "exit_index": 21, "net_return_pct": 90},
                   {"decision_index": 21, "exit_index": 24, "net_return_pct": 3}]}}
    evaluation = {"status": "COMPLETE", "self_test": {"checks": {
        "validation_gate": False, "beats_validation_buy_and_hold_after_costs": True,
        "validation_only_selection": True, "point_in_time_entries": True,
        "frozen_oos_gate": True}}}
    result = audit_backtest(profile, evaluation)
    assert result["phases"]["validation"]["trades"] == 1
    assert result["phases"]["validation"]["expectancy_pct"] == -2
    assert result["phases"]["validation"]["intraday_order_ambiguous"] == 1
    assert result["phases"]["test"]["trades"] == 1
    assert result["validation_passed"] is False
    assert result["phases"]["validation"]["sharpe_per_trade"] is None
