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

    def train_symbol_entry_profile(
        self,
        records: Iterable[dict[str, Any]],
        *,
        symbol: str,
        years: int = 10,
        initial_history: int = 20,
        evaluation_window: int = 30,
        transaction_cost_pct: float = 0.35,
        source_metadata: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Run the per-symbol adaptive long-entry learner and save its audit."""

        return self.training_service.train_symbol_entry_profile(
            records,
            symbol=symbol,
            years=years,
            initial_history=initial_history,
            evaluation_window=evaluation_window,
            transaction_cost_pct=transaction_cost_pct,
            source_metadata=source_metadata,
            persist=persist,
        )

    def record_outcome(self, **kwargs: Any) -> str:
        """Record the realized result of a previous prediction."""

        return self.training_service.record_outcome(**kwargs)


__all__ = ["AIService", "AITrainingService", "TrainingConfig"]
