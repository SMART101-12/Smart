from datetime import date, timedelta

from smart.flow_analysis import analyze_flow


def _bars():
    start = date(2026, 9, 1)
    return [{"date": (start + timedelta(days=i)).strftime("%Y%m%d"),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000 if i < 24 else 2000}
            for i in range(25)]


def test_price_volume_proxy_is_not_called_individual_inflow():
    result = analyze_flow(_bars(), symbol="TEST", as_of=date(2026, 9, 25))
    assert result["status"] == "PARTIAL"
    assert result["signal"] == "UNAVAILABLE"
    assert result["price_volume_proxy"]["signal"] == "BULLISH"


def test_observed_outflow_conflicts_with_price_volume_and_future_is_rejected():
    obs = {"source": "TSETMC ClientType", "date": "20260925",
           "buy_individual_volume": 400, "sell_individual_volume": 900,
           "buy_individual_count": 10, "sell_individual_count": 20}
    result = analyze_flow(_bars(), symbol="TEST", as_of=date(2026, 9, 25), client_type=obs)
    assert result["status"] == "CONFLICTING"
    assert "rising_price_volume_with_individual_outflow" in result["conflicts"]
    obs["date"] = "20260926"
    assert analyze_flow(_bars(), symbol="TEST", as_of=date(2026, 9, 25),
                        client_type=obs)["observed_client_type"]["status"] == "UNAVAILABLE"
