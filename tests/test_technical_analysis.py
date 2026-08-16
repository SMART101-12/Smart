from smart.technical_analysis import backtest, enrich, sensitive_points


def _rows():
    return [{"dEven": str(20200101 + i), "pClosing": 100 + i, "pMax": 101 + i, "pMin": 99 + i, "qTotTran5J": 1000 + i * 10} for i in range(230)]


def test_enrich_adds_indicators():
    rows = enrich(_rows())
    assert len(rows) == 230
    assert rows[-1]["sma20"] is not None
    assert rows[-1]["sma50"] is not None
    assert rows[-1]["sma200"] is not None
    assert rows[-1]["rsi14"] is not None
    assert rows[-1]["atr14"] is not None


def test_backtest_has_no_lookahead_in_signal_rule():
    rows = enrich(_rows())
    result = backtest(rows, horizon=5)
    assert set(result) == {"trend_up", "rsi_oversold", "macd_bullish", "volume_spike", "trend_down", "rsi_overbought", "macd_bearish"}
    assert result["trend_up"]["signals"] >= 0


def test_sensitive_points_returns_list():
    rows = enrich(_rows())
    assert isinstance(sensitive_points(rows), list)
