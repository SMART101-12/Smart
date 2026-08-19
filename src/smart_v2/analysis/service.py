from __future__ import annotations

from typing import Any


class AnalysisService:
    """Analysis boundary. Consumes processed datasets and AI outputs only."""

    def analyze(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(record) for record in records]
