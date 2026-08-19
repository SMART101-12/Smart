from __future__ import annotations

from typing import Any


class AnalysisService:
    """Analysis boundary. Consumes processed datasets and AI outputs only."""

    def analyze(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        previous_close: float | None = None

        for record in records:
            item = dict(record)
            processing = item.get("processing", {})
            derived = processing.get("derived", {})
            close = derived.get("close")

            analysis = {
                "status": "ANALYZED",
                "derived": {
                    "daily_return": None,
                },
            }

            if close is not None and previous_close not in (None, 0):
                analysis["derived"]["daily_return"] = (
                    float(close) / float(previous_close)
                ) - 1.0

            item["analysis"] = analysis
            output.append(item)

            if close is not None:
                previous_close = float(close)

        return output
