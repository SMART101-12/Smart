# -*- coding: utf-8 -*-
"""Tests for smart_v2.analysis modules."""
import numpy as np
import pandas as pd
import pytest

from src.smart_v2.analysis import SmartMoneyAnalyzer, GoldFundAnalyzer, MultiFactorEngine


def make_df(n=60, seed=7, drift=0.001):
    rng = np.random.default_rng(seed)
    close = 1000 * np.exp(np.cumsum(rng.normal(drift, 0.02, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    low = np.minimum(low, close)
    high = np.maximum(high, close)
    open_ = np.roll(close, 1); open_[0] = close[0]
    vol = rng.integers(1e6, 5e6, n).astype(float)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def test_smart_money_basic():
    r = SmartMoneyAnalyzer().analyze(make_df(), "TEST1")
    assert 0 <= r.score <= 100
    assert 0 <= r.buy_ratio <= 1


def test_smart_money_missing_columns():
    with pytest.raises(ValueError):
        SmartMoneyAnalyzer().analyze(pd.DataFrame({"close": [1, 2]}))


def test_gold_fund():
    df = make_df()
    nav = df["close"] / 1000
    r = GoldFundAnalyzer().analyze(df, "GOLD", nav)
    assert r.trend in ("up", "down", "neutral")


def test_engine_composite():
    df = make_df()
    nav = df["close"] / 1000
    r = MultiFactorEngine().run(df, "TEST1", nav)
    assert 0 <= r.composite <= 100
    assert any(f.name == "gold_fund" for f in r.factors)
