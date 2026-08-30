from __future__ import annotations

from typing import Any, Iterable

from .training import AITrainingService, TrainingConfig


class AIService:
    """AI boundary. Models consume processed snapshots and never fetch data."""

    def __init__(self, *, training_service: AITrainingService | None = None) -> None:
        self.training_service = training_service or AITrainingService()

    def predict(self, features: list[dict[str, Any]], model: Any) -> list[Any]:
        return model.predict(features)

    def train(
        self,
        records: Iterable[dict[str, Any]],
        *,
        symbol: str = "",
        config: TrainingConfig | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a leakage-safe train/validation/test experiment artifact."""

        return self.training_service.train(
            records,
            symbol=symbol,
            config=config,
            run_id=run_id,
        )

    def record_outcome(self, **kwargs: Any) -> str:
        """Record the realized result of a previous prediction."""

        return self.training_service.record_outcome(**kwargs)


__all__ = ["AIService", "AITrainingService", "TrainingConfig"]
