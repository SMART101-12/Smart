import pytest

from smart.risk import portfolio_summary, position_size


def test_position_size_respects_risk_and_allocation_caps():
    result = position_size(
        account_equity=100_000,
        risk_percent=1,
        entry=100,
        stop=90,
        target=120,
        max_allocation_percent=5,
    )
    assert result["risk_budget"] == 1000
    assert result["units"] == 50
    assert result["notional"] == 5000
    assert result["capped_by_allocation"] is True
    assert result["risk_reward"] == 2.0


def test_position_size_rejects_invalid_long_plan():
    with pytest.raises(ValueError, match="stop"):
        position_size(1000, 1, 100, 101)
    with pytest.raises(ValueError, match="target"):
        position_size(1000, 1, 100, 90, target=99)


def test_portfolio_summary_reports_pnl_and_concentration():
    result = portfolio_summary([
        {"symbol": "AAA", "quantity": 10, "entry": 100, "current": 110, "stop": 95},
        {"symbol": "BBB", "quantity": 5, "entry": 100, "current": 90},
    ])
    assert result["position_count"] == 2
    assert result["market_value"] == 1550
    assert result["unrealized_pnl"] == 50
    assert result["return_pct"] == pytest.approx(3.333333, rel=1e-6)
    assert result["largest_allocation_percent"] == pytest.approx(70.967742, rel=1e-6)

