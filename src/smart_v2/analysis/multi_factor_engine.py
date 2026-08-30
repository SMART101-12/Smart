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
    decision: str = "HOLD"
    risk_level: str = "Medium"

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "composite": self.composite,
            "factors": [
                {"name": item.name, "weight": item.weight, "value": item.value}
                for item in self.factors
            ],
            "decision": self.decision,
            "risk_level": self.risk_level,
        }


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
        composite = round(composite, 2)
        decision = "BUY" if composite >= 65 else "SELL" if composite <= 35 else "HOLD"
        risk_level = (
            "Low"
            if composite >= 70 or composite <= 30
            else "Medium"
            if 45 <= composite <= 55
            else "High"
        )
        return EngineResult(
            symbol=symbol,
            composite=composite,
            factors=factors,
            decision=decision,
            risk_level=risk_level,
        )

    def calculate_composite_score(
        self,
        *,
        technical_score: float = 50.0,
        fundamental_score: float = 50.0,
        smart_money_score: float = 50.0,
        macro_score: float = 50.0,
        risk_score: float | None = None,
    ) -> dict:
        """Compatibility scoring contract for scalar app inputs.

        This method is intentionally separate from :meth:`run`, which consumes
        an OHLCV frame.  Values are clipped to the documented 0..100 range and
        the result remains a decision-support score, not an order instruction.
        """

        values = {
            "technical": float(np.clip(technical_score, 0, 100)),
            "fundamental": float(np.clip(fundamental_score, 0, 100)),
            "smart_money": float(np.clip(smart_money_score, 0, 100)),
            "macro": float(np.clip(macro_score, 0, 100)),
        }
        weights = {"technical": 0.35, "fundamental": 0.25, "smart_money": 0.25, "macro": 0.15}
        composite = round(sum(values[name] * weights[name] for name in values), 2)
        if risk_score is None:
            risk_score = 50.0
        risk_score = float(np.clip(risk_score, 0, 100))
        risk_level = "Low" if risk_score <= 33 else "High" if risk_score >= 67 else "Medium"
        return {
            "composite_score": composite,
            "decision": "BUY" if composite >= 65 else "SELL" if composite <= 35 else "HOLD",
            "risk_level": risk_level,
            "components": values,
            "weights": weights,
            "risk_score": risk_score,
        }
