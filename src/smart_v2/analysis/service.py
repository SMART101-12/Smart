from __future__ import annotations

from typing import Any

from .gold_fund import GoldFundAnalyzer
from .multi_factor_engine import MultiFactorEngine
from .stock_service import StockAnalysisService
from .trade_plan import EntryExitEngine
from .output_formatter import AnalysisOutputFormatter


class AnalysisService:
    """Analysis boundary. Consumes processed datasets and AI outputs only."""

    def trade_plan(self, records: list[dict[str, Any]], symbol: str, tf: str = "1d") -> dict[str, Any]:
        return EntryExitEngine().generate(records, symbol, tf).as_dict()

    def report(self, records: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return AnalysisOutputFormatter().format(self.analyze_stock(records, **kwargs))

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

    def analyze_stock(self, records: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Run the integrated stock analysis on daily rows."""

        return StockAnalysisService().analyze(records, **kwargs)

    def analyze_history(self, records: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Alias used by callers that distinguish history from snapshots."""

        return self.analyze_stock(records, **kwargs)


__all__ = [
    "AnalysisService",
    "GoldFundAnalyzer",
    "MultiFactorEngine",
    "StockAnalysisService",
]
