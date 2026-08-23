from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

WEIGHTS = {
    "xau_momentum": 0.25,
    "dxy": 0.15,
    "us10y": 0.10,
    "real_yield": 0.10,
    "fed_expectations": 0.10,
    "geopolitics": 0.10,
    "central_banks": 0.07,
    "etf_flows": 0.05,
    "oil_inflation": 0.04,
}


@dataclass(frozen=True)
class GoldScore:
    score: float
    regime: str
    coverage: float
    contributions: dict[str, float]


def classify(score: float) -> str:
    if score >= 0.60:
        return "BULLISH_STRONG"
    if score >= 0.25:
        return "BULLISH"
    if score > -0.25:
        return "NEUTRAL"
    if score > -0.60:
        return "BEARISH"
    return "BEARISH_STRONG"


def score_factors(factors: Mapping[str, float | None]) -> GoldScore:
    """Score factors where +1 is maximally supportive and -1 maximally negative.

    Missing factors are excluded and weights are renormalized. The coverage ratio
    is retained so a strong score from sparse data cannot be mistaken for a full
    confidence signal.
    """
    available = {k: float(v) for k, v in factors.items() if k in WEIGHTS and v is not None}
    if not available:
        raise ValueError("no usable gold factors")
    total_weight = sum(WEIGHTS[k] for k in available)
    contributions = {k: WEIGHTS[k] * available[k] for k in available}
    score = sum(contributions.values()) / total_weight
    coverage = total_weight / sum(WEIGHTS.values())
    return GoldScore(
        score=round(max(-1.0, min(1.0, score)), 6),
        regime=classify(score),
        coverage=round(coverage, 6),
        contributions={k: round(v / total_weight, 6) for k, v in contributions.items()},
    )
