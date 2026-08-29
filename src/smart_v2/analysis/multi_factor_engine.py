# -*- coding: utf-8 -*-
"""Multi-factor scoring engine (smart_v2)."""
from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
import pandas as pd

from .smart_money import SmartMoneyAnalyzer
from .gold_fund import GoldFundAnalyzer


@dataclass
class FactorScore:
    name: str
    weight: float
    value: float  # 0..100


@dataclass
class EngineResult:
    symbol: str
    composite: float = 0.0
    factors: List[FactorScore] = field(default_factory=list)


class MultiFactorEngine:
    """Combines smart-money, gold-fund and momentum/value factors."""

    DEFAULT_WEIGHTS = {"smart_money": 0.4, "gold_fund": 0.2,
                       "momentum": 0.25, "value": 0.15}

    def __init__(self, weights: Dict[str, float] | None = None):
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.sm = SmartMoneyAnalyzer()

    @staticmethod
    def _momentum(df: pd.DataFrame, lookback: int = 20) -> float:
        c = df["close"]
        if len(c) < 2:
            return 50.0
        ret = float(c.iloc[-1] / c.iloc[-min(lookback, len(c))] - 1)
        return float(np.clip(50 + 200 * np.tanh(ret), 0, 100))

    @staticmethod
    def _value(df: pd.DataFrame, nav: pd.Series | None) -> float:
        if nav is None or len(nav) < 2:
            return 50.0
        prem = float(df["close"].iloc[-1] / nav.iloc[-1])
        return float(np.clip(50 - 100 * np.tanh(prem - 1), 0, 100))

    def run(self, df: pd.DataFrame, symbol: str = "",
            nav: pd.Series | None = None) -> EngineResult:
        sm_res = self.sm.analyze(df, symbol)
        factors = [
            FactorScore("smart_money", self.weights["smart_money"], sm_res.score),
            FactorScore("momentum", self.weights["momentum"], self._momentum(df)),
            FactorScore("value", self.weights["value"], self._value(df, nav)),
        ]
        if nav is not None:
            gf = GoldFundAnalyzer().analyze(df, symbol, nav)
            factors.insert(1, FactorScore("gold_fund", self.weights["gold_fund"], gf.score))
        else:
            factors = [f for f in factors if f.name != "gold_fund"]
        wsum = sum(f.weight for f in factors) or 1.0
        composite = float(sum(f.value * f.weight for f in factors) / wsum)
        return EngineResult(symbol=symbol, composite=round(composite, 2), factors=factors)
