from datetime import datetime, timezone

from smart.models import MarketDataPoint


def test_market_data_point_is_normalized_container():
    row = MarketDataPoint(
        symbol="TEST",
        timestamp=datetime.now(timezone.utc),
        source="unit-test",
        price=100.0,
        volume=2_000_000,
    )
    assert row.symbol == "TEST"
    assert row.price == 100.0
