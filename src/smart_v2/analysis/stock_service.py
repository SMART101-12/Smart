"""Integrated, point-in-time stock analysis for SMART V2.

This service is intentionally downstream-only: it accepts rows already
downloaded and validated by the acquisition/archive layers.  It does not make
network calls and it does not manufacture missing market values.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from smart.archive import deduplicate_rows, safe_symbol
from smart.meta_ensemble import evaluate as evaluate_predictions
from smart.meta_ensemble import predict_at, walk_forward
from smart.risk import trade_plan

from .multi_factor_engine import MultiFactorEngine


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if np.isfinite(result) else default


class StockAnalysisService:
    """Run the SMART technical, flow, factor and forecast layers together."""

    def __init__(self, engine: MultiFactorEngine | None = None) -> None:
        self.engine = engine or MultiFactorEngine()

    @staticmethod
    def to_frame(
        rows: Iterable[dict[str, Any]],
        *,
        symbol: str = "",
        ins_code: str = "",
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        canonical, _ = deduplicate_rows(
            (
                StockAnalysisService._flatten_row(row)
                for row in rows
                if isinstance(row, dict)
            ),
            symbol=symbol,
            ins_code=ins_code,
            source="TSETMC",
        )
        canonical = [
            item for item in canonical
            if (_as_float(item.get("close"), 0.0) or 0.0) > 0
        ]
        if not canonical:
            raise ValueError("No valid OHLCV rows were supplied")

        frame = pd.DataFrame(canonical)
        frame["date"] = pd.to_datetime(frame["source_date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).set_index("date").sort_index()
        for column in ("open", "high", "low", "close", "volume", "value", "trades"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame["close"] = frame["close"].where(frame["close"] > 0)
        # High/low/open are allowed to be absent in older archives.  Filling
        # them from close is a transparent fallback for indicator geometry,
        # while the quality report still marks the original field as absent.
        for column in ("open", "high", "low"):
            frame[column] = frame[column].where(frame[column].notna(), frame["close"])
        frame["volume"] = frame["volume"].fillna(0.0).clip(lower=0.0)
        frame["value"] = frame["value"].fillna(0.0).clip(lower=0.0)
        frame["trades"] = frame["trades"].fillna(0.0).clip(lower=0.0)
        frame = frame.dropna(subset=["close"])
        return frame, canonical

    @staticmethod
    def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
        """Accept raw rows and V2 processed records through one adapter."""

        flattened = dict(row)
        record = row.get("record")
        if isinstance(record, dict):
            flattened = {**record, **flattened}
        processing = row.get("processing")
        if isinstance(processing, dict):
            derived = processing.get("derived")
            if isinstance(derived, dict):
                flattened = {**derived, **flattened}
        return flattened

    @staticmethod
    def _meta_rows(canonical: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expose canonical fields under the legacy meta-ensemble names."""

        result: list[dict[str, Any]] = []
        for item in canonical:
            result.append(
                {
                    **item,
                    "dEven": item.get("date"),
                    "pClosing": item.get("close"),
                    "pDrCotVal": item.get("last_price") or item.get("close"),
                    "pMax": item.get("high"),
                    "pMin": item.get("low"),
                    "pFirst": item.get("open"),
                    "qTotTran5J": item.get("volume"),
                    "qTotCap": item.get("value"),
                    "zTotTran": item.get("trades"),
                }
            )
        return result

    @staticmethod
    def _atr(frame: pd.DataFrame, period: int = 14) -> float:
        high = frame["high"].to_numpy(dtype=float)
        low = frame["low"].to_numpy(dtype=float)
        close = frame["close"].to_numpy(dtype=float)
        if len(close) < 2:
            return 0.0
        previous = np.roll(close, 1)
        previous[0] = close[0]
        true_range = np.maximum.reduce(
            [high - low, np.abs(high - previous), np.abs(low - previous)]
        )
        return float(np.mean(true_range[-period:])) if len(true_range) else 0.0

    @staticmethod
    def _quality(canonical: list[dict[str, Any]]) -> dict[str, Any]:
        required = ("open", "high", "low", "close", "volume")
        missing = {
            field: sum(item.get(field) is None for item in canonical)
            for field in required
        }
        missing = {key: value for key, value in missing.items() if value}
        return {
            "status": "PASS" if not missing else "DEGRADED",
            "rows": len(canonical),
            "missing_field_counts": missing,
            "raw_values_preserved": True,
        }

    def analyze(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        symbol: str = "",
        ins_code: str = "",
        nav: pd.Series | Iterable[float] | None = None,
        global_context: dict[str, Any] | None = None,
        include_history_metrics: bool = True,
        max_metrics_rows: int = 750,
    ) -> dict[str, Any]:
        frame, canonical = self.to_frame(rows, symbol=symbol, ins_code=ins_code)
        nav_series = None
        if nav is not None:
            if isinstance(nav, pd.Series):
                nav_series = pd.to_numeric(nav, errors="coerce")
            else:
                values = list(nav)[-len(frame) :]
                nav_series = pd.Series(values, index=frame.index[-len(values) :])
        engine_result = self.engine.run(frame, symbol=symbol, nav=nav_series)
        meta_rows = self._meta_rows(canonical)
        latest_prediction = None
        historical_metrics = None
        if len(meta_rows) >= 50:
            latest_prediction_obj = predict_at(meta_rows, len(meta_rows) - 1)
            if latest_prediction_obj is not None:
                latest_prediction = latest_prediction_obj.to_dict()
            if include_history_metrics and len(meta_rows) >= 56:
                metric_rows = (
                    meta_rows
                    if max_metrics_rows <= 0
                    else meta_rows[-max(max_metrics_rows, 56):]
                )
                predictions = walk_forward(metric_rows, horizon=5)
                historical_metrics = evaluate_predictions(predictions)

        latest = canonical[-1]
        close = float(latest["close"])
        atr_value = self._atr(frame)
        stop = close - 1.5 * atr_value if atr_value > 0 else None
        target = close + 3.0 * atr_value if atr_value > 0 else None
        plan = None
        if stop is not None and target is not None and stop > 0:
            plan = trade_plan(close, stop, target)

        composite = float(engine_result.composite)
        action = (
            "positive_watch"
            if composite >= 65
            else "negative_watch"
            if composite <= 35
            else "neutral_watch"
        )
        return {
            "schema_version": "1.0",
            "status": "ANALYZED",
            "symbol": symbol or str(latest.get("symbol") or ""),
            "ins_code": ins_code or str(latest.get("ins_code") or ""),
            "as_of": latest.get("source_date"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_quality": self._quality(canonical),
            "latest": latest,
            "factor_engine": {
                "symbol": engine_result.symbol,
                "composite": engine_result.composite,
                "decision": engine_result.decision,
                "risk_level": engine_result.risk_level,
                "factors": [asdict(item) for item in engine_result.factors],
            },
            "decision_support": {
                "action": action,
                "atr": round(atr_value, 8),
                "trade_plan": plan,
                "disclaimer": "Research signal only; not an execution instruction.",
            },
            "forecast": latest_prediction,
            "historical_forecast_metrics": historical_metrics,
            "global_context": global_context or {},
            "lineage": {
                "source": str(latest.get("source") or "TSETMC"),
                "rows_used": len(canonical),
                "point_in_time": True,
                "future_rows_used_for_current_signal": False,
            },
        }

    def analyze_and_save(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        symbol: str,
        output_root: str | Path = "runtime/analysis",
        **kwargs: Any,
    ) -> dict[str, Any]:
        report = self.analyze(rows, symbol=symbol, **kwargs)
        target = Path(output_root) / safe_symbol(symbol) / "latest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report["artifact_path"] = str(target)
        return report

    def analyze_path(
        self,
        path: str | Path,
        *,
        symbol: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Load one SMART archive JSON file and analyze its daily rows.

        This convenience boundary accepts both the legacy ``daily_history``
        layout and the canonical ``records`` layout.  It deliberately does
        not perform network access or mutate the source archive.
        """

        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError(f"Archive payload must be an object: {source}")
        rows = payload.get("records") or payload.get("daily_history") or []
        if not isinstance(rows, list):
            raise ValueError(f"Archive has no daily rows: {source}")
        resolved_symbol = symbol or str(payload.get("symbol") or source.parent.name)
        ins_code = str(payload.get("ins_code") or "")
        return self.analyze(
            rows,
            symbol=resolved_symbol,
            ins_code=ins_code,
            **kwargs,
        )


__all__ = ["StockAnalysisService"]
