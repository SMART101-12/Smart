# -*- coding: utf-8 -*-
"""Gold-fund analysis for TSETMC gold ETFs / funds (smart_v2)."""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class GoldFundResult:
    symbol: str
    nav_premium: float = 0.0
    trend: str = "neutral"
    volatility: float = 0.0
    score: float = 0.0


class GoldFundAnalyzer:
    """Compares fund price behaviour vs. NAV and computes trend/vol metrics."""

    def __init__(self, window: int = 30, vol_floor: float = 1e-9):
        self.window = window
        self.vol_floor = vol_floor

    def analyze(self, df: pd.DataFrame, symbol: str = "",
                nav_series: pd.Series | None = None) -> GoldFundResult:
        df = df.sort_index().tail(self.window)
        rets = df["close"].pct_change().dropna()
        volatility = float(rets.std() * np.sqrt(252)) if len(rets) > 1 else 0.0

        nav_premium = 0.0
        if nav_series is not None and len(nav_series) > 1:
            nav = nav_series.sort_index().tail(len(df))
            if len(nav) == len(df):
                base = float(nav.iloc[0]) or self.vol_floor
                implied = df["close"].iloc[0] * (nav / base)
                with np.errstate(divide="ignore", invalid="ignore"):
                    prem = (df["close"] - implied) / implied
                nav_premium = float(prem.iloc[-1])

        sma_f = df["close"].rolling(5).mean().iloc[-1]
        sma_s = df["close"].rolling(min(20, len(df))).mean().iloc[-1]
        trend = "up" if sma_f > sma_s else ("down" if sma_f < sma_s else "neutral")

        mom = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
        score = float(np.clip(50 + 100 * mom - 200 * abs(nav_premium), 0, 100))
        return GoldFundResult(symbol=symbol, nav_premium=nav_premium,
                              trend=trend, volatility=volatility, score=score)
