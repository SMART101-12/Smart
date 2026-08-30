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

    def analyze(
        self,
        df: pd.DataFrame | None = None,
        symbol: str = "",
        nav_series: pd.Series | None = None,
        *,
        fund_price: float | None = None,
        nav_per_unit: float | None = None,
        gold_oz_usd: float | None = None,
        usd_irr_rate: float | None = None,
    ) -> GoldFundResult | dict:
        # Scalar mode is useful for a live fund quote when a historical frame
        # is not available.  Keeping it on the same public method preserves
        # compatibility with early SMART app callers.
        if df is None:
            if fund_price is None or nav_per_unit is None:
                raise ValueError("df or fund_price/nav_per_unit must be supplied")
            return self.evaluate_snapshot(
                fund_price=fund_price,
                nav_per_unit=nav_per_unit,
                gold_oz_usd=gold_oz_usd,
                usd_irr_rate=usd_irr_rate,
            )
        if not isinstance(df, pd.DataFrame) or df.empty:
            raise ValueError("df must be a non-empty DataFrame")
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

    def evaluate_snapshot(
        self,
        *,
        fund_price: float,
        nav_per_unit: float,
        gold_oz_usd: float | None = None,
        usd_irr_rate: float | None = None,
    ) -> dict:
        """Evaluate one fund quote when a historical OHLCV frame is unavailable."""

        fund_price = float(fund_price)
        nav_per_unit = float(nav_per_unit)
        if fund_price <= 0 or nav_per_unit <= 0:
            raise ValueError("fund_price and nav_per_unit must be positive")
        bubble_percent = (fund_price / nav_per_unit - 1.0) * 100.0
        # A premium is a warning, not an automatic sell signal.  The optional
        # macro values are retained as context and are never invented.
        if bubble_percent >= 8:
            decision, risk = "SELL", "High"
        elif bubble_percent <= -5:
            decision, risk = "BUY", "Medium"
        else:
            decision, risk = "HOLD", "Low" if abs(bubble_percent) < 3 else "Medium"
        return {
            "decision": decision,
            "risk": risk,
            "risk_level": risk,
            "bubble_percent": round(bubble_percent, 4),
            "fund_price": fund_price,
            "nav_per_unit": nav_per_unit,
            "gold_oz_usd": gold_oz_usd,
            "usd_irr_rate": usd_irr_rate,
            "source_quality": "provided_snapshot",
        }
