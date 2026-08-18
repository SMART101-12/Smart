from smart.technical_analysis import Bar, build_features, rsi, sma


def _bars(n=80):
    return [
        Bar(
            date=f"202001{i:02d}", close=100 + i * 0.5 + (i % 7) * 0.2,
            high=101 + i * 0.5 + (i % 7) * 0.2,
            low=99 + i * 0.5 + (i % 7) * 0.2,
            open=100 + i * 0.5,
            volume=1000 + i * 10, value=100000, trades=100,
        ) for i in range(1, n + 1)
    ]


def test_sma_warmup_and_values():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_rsi_has_warmup_then_values():
    values = [100 + i for i in range(20)]
    result = rsi(values, 14)
    assert result[:14] == [None] * 14
    assert result[14] == 100.0


def test_walk_forward_does_not_score_before_indicator_warmup():
    features = build_features(_bars())
    assert len(features) == 80
    assert features[0].sma20 is None
    assert features[18].sma20 is None
    assert features[19].sma20 is not None
    assert features[19].future_return_5d is not None


def test_breakout_uses_prior_window_not_current_close():
    bars = _bars(30)
    features = build_features(bars)
    assert features[19].breakout_up20 is False
    assert features[20].breakout_up20 is False
