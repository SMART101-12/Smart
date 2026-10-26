from datetime import date, timedelta

import pytest

from smart.flow_analysis import analyze_flow


def fixture():
    bars, history = [], []
    for i in range(20):
        day = (date(2026, 9, 1) + timedelta(days=i)).isoformat()
        bars.append(dict(date=day, open=100, high=110, low=90, close=100+i/10,
                         volume=100, value=10000))
        history.append(dict(date=day, buy_individual_volume=70, sell_individual_volume=40,
                            buy_corporate_volume=30, sell_corporate_volume=60,
                            buy_individual_count=7, sell_individual_count=8,
                            buy_corporate_count=3, sell_corporate_count=6))
    observation = dict(history[-1], source="TSETMC ClientType", history=history)
    return bars, observation


def run(bars, observation):
    return analyze_flow(bars, symbol="TEST", as_of=date(2026, 9, 20),
                        client_type=observation)["money_flow"]


def test_dated_flow_units_opposite_groups_power_and_full_windows():
    bars, obs = fixture()
    result = run(bars, obs)
    latest = result["latest"]
    assert latest["net_individual_volume"] == 30
    assert latest["net_individual_value_estimate"] == 3000
    assert latest["net_corporate_value_estimate"] == -3000
    assert latest["individual_buy_power"] == 2
    assert latest["individual_buy_per_capita_value_estimate"] == 1000
    assert result["windows"]["20"]["net_individual_value_estimate"] == 60000
    assert result["value_quality"] == "ESTIMATED" and result["unit"] == "IRR"


@pytest.mark.parametrize("change", ["missing_day", "conflict", "future"])
def test_gaps_conflicts_and_future_are_never_filled(change):
    bars, obs = fixture()
    if change == "missing_day":
        obs["history"].pop(10)
    elif change == "conflict":
        obs["history"][10]["buy_corporate_volume"] = 999
    else:
        obs["history"][10]["date"] = "2026-09-21"
    result = run(bars, obs)
    assert result["windows"]["20"]["status"] == "INSUFFICIENT"
    assert result["windows"]["20"]["net_individual_value_estimate"] is None
    assert len(result["history"]) == 19


@pytest.mark.parametrize("value", [None, 0, float("nan"), 1000000])
def test_missing_or_invalid_turnover_never_becomes_cash_flow(value):
    bars, obs = fixture()
    bars[-1]["value"] = value
    result = run(bars, obs)
    assert result["latest"]["net_individual_volume"] == 30
    assert result["latest"]["net_individual_value_estimate"] is None
    assert result["windows"]["5"]["net_individual_value_estimate"] is None


def test_zero_count_is_not_infinite_power():
    bars, obs = fixture()
    obs["history"][-1]["buy_individual_count"] = 0
    assert run(bars, obs)["latest"]["individual_buy_power"] is None


def test_actual_trade_values_override_volume_direction_and_reach_decision_signal():
    bars, obs = fixture()
    for item in obs["history"]:
        item.update(buy_individual_value=3000, sell_individual_value=5000,
                    buy_corporate_value=7000, sell_corporate_value=5000)
    result = analyze_flow(bars, symbol="TEST", as_of=date(2026, 9, 20), client_type=obs)
    money = result["money_flow"]
    assert money["latest"]["net_individual_value"] == -2000
    assert money["latest"]["net_individual_value_estimate"] == 3000
    assert money["windows"]["20"]["net_individual_value"] == -40000
    assert money["value_quality"] == "OBSERVED"
    assert result["observed_client_type"]["signal"] == "BEARISH"


def test_inconsistent_actual_values_block_confirmation():
    bars, obs = fixture()
    obs["history"][-1].update(buy_individual_value=9000, sell_individual_value=5000,
                             buy_corporate_value=7000, sell_corporate_value=5000)
    result = analyze_flow(bars, symbol="TEST", as_of=date(2026, 9, 20), client_type=obs)
    assert result["money_flow"]["latest"]["net_individual_value"] is None
    assert "client_type_value_totals_mismatch" in result["conflicts"]
