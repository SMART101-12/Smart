from datetime import date, timedelta

import pytest

from smart.market_models import analyze_market_models


def observed(count=110):
    start = date(2025, 1, 1)
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "open": 100 + i * .4, "high": 102 + i * .4,
             "low": 99 + i * .4, "close": 101 + i * .4,
             "volume": 1000 + (i % 10) * 10} for i in range(count)]


def test_ten_independent_lenses_with_audited_candles():
    rows = observed()
    rows[20] = {**rows[20], "open": 0, "high": 0, "low": 0, "volume": 0}
    result = analyze_market_models(rows, symbol="TEST")
    assert result["status"] == "available"
    assert len(result["models"]) == len({m["id"] for m in result["models"]}) == 10
    assert result["data_quality"]["excluded_ohlcv_rows"] == 1
    assert all(m["signal"] in {"bullish", "bearish", "neutral", "unavailable"} for m in result["models"])
    cloud = next(m for m in result["models"] if m["id"] == "ichimoku")["metrics"]
    valid = [row for i, row in enumerate(rows) if i != 20]
    expected = (max(row["high"] for row in valid[-78:-26])
                + min(row["low"] for row in valid[-78:-26])) / 2
    assert cloud["cloud_b"] == pytest.approx(expected)
    assert result["counts"]["bullish"] + result["counts"]["bearish"] + result["counts"]["neutral"] + result["counts"]["unavailable"] == 10


def test_short_or_stale_data_never_creates_votes():
    short = analyze_market_models(observed(14), symbol="TEST")
    assert len(short["models"]) == 10
    assert all(m["signal"] == "unavailable" for m in short["models"])
    rows = observed()
    rows[-1] = {**rows[-1], "open": 0, "high": 0, "low": 0}
    stale = analyze_market_models(rows, symbol="TEST")
    assert stale["status"] == "unavailable"
    assert stale["data_quality"]["latest_bar_verified"] is False
    assert all(m["signal"] == "unavailable" for m in stale["models"])
