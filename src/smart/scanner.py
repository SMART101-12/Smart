"""First-pass market scanner and explainable ranking engine."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class Candidate:
    symbol: str
    price: float | None = None
    volume_ratio: float | None = None
    value_ratio: float | None = None
    smart_money_score: float = 0.0
    technical_score: float = 0.0
    liquidity_score: float = 0.0
    data_quality_score: float = 0.0

    @property
    def score(self) -> float:
        """Weighted MVP score; weights will become regime-adaptive later."""
        return round(
            0.30 * self.smart_money_score
            + 0.30 * self.technical_score
            + 0.20 * self.liquidity_score
            + 0.20 * self.data_quality_score,
            2,
        )


def rank_candidates(candidates: Iterable[Candidate], limit: int = 10) -> list[dict]:
    """Return explainable Top-N ranking."""
    ranked = sorted(candidates, key=lambda x: x.score, reverse=True)[:limit]
    return [
        {**asdict(c), "score": c.score, "rank": i}
        for i, c in enumerate(ranked, start=1)
    ]


def initial_analysis(candidates: Iterable[Candidate]) -> dict:
    """Produce the first decision-support output without pretending to trade."""
    top10 = rank_candidates(candidates, 10)
    return {
        "status": "ok",
        "stage": "scanner_mvp",
        "top10": top10,
        "recommended_count": min(3, len(top10)),
        "note": "MVP ranking only; live-source validation is required before a trade decision.",
    }
