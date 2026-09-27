# -*- coding: utf-8 -*-
"""Smart Money analysis for TSETMC daily candles (smart_v2)."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np
import pandas as pd


@dataclass
class SmartMoneyResult:
    symbol: str
    score: float = 0.0
    buy_ratio: float = 0.0
    sell_ratio: float = 0.0
    net_flow: float = 0.0
    signals: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)


class SmartMoneyAnalyzer:
    """Detects institutional ('smart money') accumulation/distribution
    from volume, value, and close-position heuristics on TSETMC data."""

    def __init__(self, window: int = 20, min_volume: float = 0.0):
        self.window = window
        self.min_volume = min_volume

    @staticmethod
    def _close_position(df: pd.DataFrame) -> pd.Series:
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        return ((df["close"] - df["low"]) / rng).fillna(0.5)

    def analyze(self, df: pd.DataFrame, symbol: str = "") -> SmartMoneyResult:
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            raise ValueError(f"missing columns: {required - set(df.columns)}")
        df = df.sort_index().tail(self.window)
        if df["volume"].sum() <= self.min_volume:
            return SmartMoneyResult(symbol=symbol, signals=["insufficient-volume"])

        # value-weighted money flow proxy
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        flow = typical * df["volume"]
        up = (df["close"] > df["close"].shift(1)).fillna(False)
        buy_ratio = float(flow[up].sum() / flow.sum()) if flow.sum() else 0.0
        sell_ratio = 1.0 - buy_ratio
        cp = self._close_position(df)
        net_flow = float((flow * (cp - 0.5) * 2).sum() / flow.sum()) if flow.sum() else 0.0

        score = 50.0 + 50.0 * (buy_ratio - 0.5) * 2 + 25.0 * np.tanh(net_flow)
        score = float(np.clip(score, 0, 100))
        signals = []
        if buy_ratio > 0.6: signals.append("accumulation")
        if buy_ratio < 0.4: signals.append("distribution")
        if cp.iloc[-1] > 0.7: signals.append("strong-close")
        if cp.iloc[-1] < 0.3: signals.append("weak-close")
        return SmartMoneyResult(symbol=symbol, score=score, buy_ratio=buy_ratio,
                                sell_ratio=sell_ratio, net_flow=net_flow,
                                signals=signals, details={"window": len(df)})
