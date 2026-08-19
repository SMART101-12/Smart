from __future__ import annotations

from typing import Any


class AIService:
    """AI boundary. Models must consume processed dataset snapshots only."""

    def predict(self, features: list[dict[str, Any]], model: Any) -> list[Any]:
        return model.predict(features)
