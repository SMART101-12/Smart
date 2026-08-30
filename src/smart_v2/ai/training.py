"""Leakage-safe local training and learning memory for SMART.

This module is deliberately self-contained.  It trains a small dual-head
ridge model (direction + next-period return) from validated OHLCV rows, uses
chronological Train/Validation/Test windows, compares the result with simple
baselines, and stores every run as an immutable JSON artifact.

It is a research/decision-support component, not a promise of profitable
trading.  Future rows are used only to create labels after a point-in-time
feature snapshot has been created.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


FEATURE_NAMES = (
    "return_1d",
    "return_3d",
    "return_5d",
    "sma5_gap",
    "sma20_gap",
    "ema12_gap",
    "ema26_gap",
    "rsi14",
    "volume_ratio20",
    "range_pct",
    "volatility20",
    "drawdown20",
)

_DATE_KEYS = ("source_date", "date", "dEven", "market_date")


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip().replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _row_date(row: dict[str, Any]) -> date | None:
    for key in _DATE_KEYS:
        parsed = _parse_date(row.get(key))
        if parsed:
            return parsed
    for nested_key in ("record", "processing"):
        nested = row.get(nested_key)
        if isinstance(nested, dict):
            source = nested.get("derived") if nested_key == "processing" else nested
            if isinstance(source, dict):
                for key in _DATE_KEYS:
                    parsed = _parse_date(source.get(key))
                    if parsed:
                        return parsed
    return None


def _number(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    sources: list[dict[str, Any]] = [row]
    record = row.get("record")
    if isinstance(record, dict):
        sources.append(record)
    processing = row.get("processing")
    if isinstance(processing, dict) and isinstance(processing.get("derived"), dict):
        sources.append(processing["derived"])
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value in (None, "", "-", ".", "NA", "N/A"):
                continue
            try:
                result = float(str(value).replace(",", "").strip())
            except (TypeError, ValueError):
                continue
            if math.isfinite(result):
                return result
    return default


def _has_number(row: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = _number(row, key, default=float("nan"))
        if math.isfinite(value):
            return True
    return False


def normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return valid, oldest-first OHLCV rows without mutating input."""

    accepted: list[tuple[date, int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        parsed = _row_date(row)
        close = _number(row, "close", "pClosing", "priceClosing", "pDrCotVal", "pcl", "pdv")
        if parsed is None or close <= 0:
            continue
        accepted.append((parsed, index, dict(row)))

    # A duplicate date is resolved deterministically by keeping the row with
    # the greatest number of populated OHLCV values, then the last source
    # occurrence.  This mirrors the canonical archive policy.
    grouped: dict[date, list[tuple[int, dict[str, Any]]]] = {}
    for parsed, index, row in accepted:
        grouped.setdefault(parsed, []).append((index, row))
    result: list[dict[str, Any]] = []
    for parsed in sorted(grouped):
        candidates = grouped[parsed]
        chosen = max(
            candidates,
            key=lambda item: (
                sum(
                    _has_number(item[1], *aliases)
                    for aliases in (
                        ("open", "pOpen", "pFirst", "priceFirst", "pf"),
                        ("high", "pHigh", "pMax", "priceMax", "pmax"),
                        ("low", "pLow", "pMin", "priceMin", "pmin"),
                        ("close", "pClosing", "priceClosing", "pDrCotVal", "pcl"),
                        ("volume", "qTotTran5J", "tvol", "qtj"),
                    )
                ),
                item[0],
            ),
        )[1]
        result.append(chosen)
    return result


def _closes(rows: Sequence[dict[str, Any]]) -> list[float]:
    return [
        _number(row, "close", "pClosing", "priceClosing", "pDrCotVal", "pcl", "pdv")
        for row in rows
    ]


def _volumes(rows: Sequence[dict[str, Any]]) -> list[float]:
    return [_number(row, "volume", "qTotTran5J", "tvol", "qtj") for row in rows]


def _mean(values: Sequence[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    return float(np.std(np.asarray(values, dtype=float), ddof=1))


def _rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = np.diff(np.asarray(values, dtype=float))[-period:]
    gains = float(np.mean(np.maximum(changes, 0.0)))
    losses = float(np.mean(np.maximum(-changes, 0.0)))
    if losses == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    value = float(np.mean(values[:period]))
    alpha = 2.0 / (period + 1.0)
    for item in values[period:]:
        value = alpha * float(item) + (1.0 - alpha) * value
    return value


def feature_snapshot(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Build features using only the rows passed to this function."""

    if not rows:
        raise ValueError("at least one row is required to build features")
    closes = _closes(rows)
    volumes = _volumes(rows)
    price = closes[-1]

    def gap(period: int) -> float:
        average = _mean(closes[-period:])
        return price / average - 1.0 if average and average > 0 else 0.0

    def return_n(period: int) -> float:
        return price / closes[-period - 1] - 1.0 if len(closes) > period and closes[-period - 1] else 0.0

    volume_average = _mean(volumes[-20:])
    range_value = _number(rows[-1], "high", "pHigh", "priceMax", "pMax", "pmax") - _number(
        rows[-1], "low", "pLow", "priceMin", "pMin", "pmin"
    )
    volatility_returns = [
        closes[i] / closes[i - 1] - 1.0
        for i in range(max(1, len(closes) - 20), len(closes))
        if closes[i - 1]
    ]
    peak = max(closes[-20:]) if closes else price
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    rsi_value = _rsi(closes, 14)
    values = {
        "return_1d": return_n(1),
        "return_3d": return_n(3),
        "return_5d": return_n(5),
        "sma5_gap": gap(5),
        "sma20_gap": gap(20),
        "ema12_gap": price / ema12 - 1.0 if ema12 else 0.0,
        "ema26_gap": price / ema26 - 1.0 if ema26 else 0.0,
        "rsi14": (rsi_value if rsi_value is not None else 50.0) / 100.0,
        "volume_ratio20": volumes[-1] / volume_average if volume_average else 0.0,
        "range_pct": range_value / price if price else 0.0,
        "volatility20": _std(volatility_returns) or 0.0,
        "drawdown20": price / peak - 1.0 if peak else 0.0,
    }
    return {name: float(values.get(name, 0.0)) for name in FEATURE_NAMES}


def build_training_dataset(
    rows: Iterable[dict[str, Any]],
    *,
    horizon: int = 1,
    min_history: int = 30,
) -> list[dict[str, Any]]:
    """Create point-in-time examples with future labels kept separate."""

    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    ordered = normalize_rows(rows)
    closes = _closes(ordered)
    examples: list[dict[str, Any]] = []
    for index in range(max(1, min_history), len(ordered) - horizon):
        current = closes[index]
        future = closes[index + horizon]
        if current <= 0:
            continue
        target_return = future / current - 1.0
        snapshot = feature_snapshot(ordered[: index + 1])
        current_date = _row_date(ordered[index])
        target_date = _row_date(ordered[index + horizon])
        if current_date is None or target_date is None:
            continue
        examples.append(
            {
                "decision_date": current_date.isoformat(),
                "target_date": target_date.isoformat(),
                "features": snapshot,
                "target_return": float(target_return),
                "target_direction": int(target_return > 0),
                "history_end_index": index,
            }
        )
    return examples


@dataclass(frozen=True)
class TrainingConfig:
    horizon: int = 1
    min_history: int = 30
    train_ratio: float = 0.60
    validation_ratio: float = 0.20
    ridge_values: tuple[float, ...] = (0.1, 1.0, 10.0)
    model_version: str = "smart-local-ridge-v1"
    feature_set_version: str = "ohlcv-point-in-time-v1"

    def __post_init__(self) -> None:
        if self.horizon < 1 or self.min_history < 1:
            raise ValueError("horizon and min_history must be positive")
        if not 0 < self.train_ratio < 1:
            raise ValueError("train_ratio must be between 0 and 1")
        if not 0 < self.validation_ratio < 1:
            raise ValueError("validation_ratio must be between 0 and 1")
        if self.train_ratio + self.validation_ratio >= 1:
            raise ValueError("train_ratio + validation_ratio must be below 1")


class TrainedLinearModel:
    """A serializable standardized ridge model with two prediction heads."""

    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        means: Sequence[float],
        scales: Sequence[float],
        direction_weights: Sequence[float],
        return_weights: Sequence[float],
        ridge: float,
        model_version: str,
    ) -> None:
        self.feature_names = tuple(feature_names)
        self.means = np.asarray(means, dtype=float)
        self.scales = np.asarray(scales, dtype=float)
        self.direction_weights = np.asarray(direction_weights, dtype=float)
        self.return_weights = np.asarray(return_weights, dtype=float)
        self.ridge = float(ridge)
        self.model_version = model_version

    @staticmethod
    def _design(features: Sequence[dict[str, Any]], names: Sequence[str]) -> np.ndarray:
        values = [
            [_safe_float(item.get(name)) for name in names]
            for item in features
        ]
        return np.asarray(values, dtype=float)

    @classmethod
    def fit(
        cls,
        features: Sequence[dict[str, Any]],
        direction_targets: Sequence[int],
        return_targets: Sequence[float],
        *,
        ridge: float,
        model_version: str,
    ) -> "TrainedLinearModel":
        if not features:
            raise ValueError("cannot fit without examples")
        names = tuple(FEATURE_NAMES)
        matrix = cls._design(features, names)
        means = np.nanmean(matrix, axis=0)
        means = np.where(np.isfinite(means), means, 0.0)
        matrix = np.where(np.isfinite(matrix), matrix, means)
        scales = np.nanstd(matrix, axis=0)
        scales = np.where(np.isfinite(scales) & (scales > 1e-12), scales, 1.0)
        standardized = (matrix - means) / scales
        design = np.column_stack([np.ones(len(standardized)), standardized])
        penalty = np.eye(design.shape[1], dtype=float) * float(ridge)
        penalty[0, 0] = 0.0

        def solve(targets: Sequence[float]) -> np.ndarray:
            left = design.T @ design + penalty
            right = design.T @ np.asarray(targets, dtype=float)
            try:
                return np.linalg.solve(left, right)
            except np.linalg.LinAlgError:
                return np.linalg.pinv(left) @ right

        return cls(
            feature_names=names,
            means=means,
            scales=scales,
            direction_weights=solve(direction_targets),
            return_weights=solve(return_targets),
            ridge=ridge,
            model_version=model_version,
        )

    def _predict_matrix(self, features: Sequence[dict[str, Any]]) -> np.ndarray:
        matrix = self._design(features, self.feature_names)
        matrix = np.where(np.isfinite(matrix), matrix, self.means)
        standardized = (matrix - self.means) / self.scales
        return np.column_stack([np.ones(len(standardized)), standardized])

    def predict(self, features: Sequence[dict[str, Any]]) -> list[dict[str, float]]:
        if not features:
            return []
        design = self._predict_matrix(features)
        probabilities = np.clip(design @ self.direction_weights, 0.0, 1.0)
        returns = design @ self.return_weights
        return [
            {
                "direction_probability": float(probability),
                "predicted_return": float(predicted_return),
                "direction": (
                    "UP"
                    if probability >= 0.55
                    else "DOWN"
                    if probability <= 0.45
                    else "NEUTRAL"
                ),
            }
            for probability, predicted_return in zip(probabilities, returns)
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_type": "standardized_ridge_dual_head",
            "model_version": self.model_version,
            "feature_names": list(self.feature_names),
            "means": self.means.tolist(),
            "scales": self.scales.tolist(),
            "direction_weights": self.direction_weights.tolist(),
            "return_weights": self.return_weights.tolist(),
            "ridge": self.ridge,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrainedLinearModel":
        """Rehydrate a model stored in a learning artifact."""

        if not isinstance(payload, dict):
            raise ValueError("model payload must be a dictionary")
        required = (
            "feature_names",
            "means",
            "scales",
            "direction_weights",
            "return_weights",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"model payload is missing: {missing}")
        return cls(
            feature_names=payload["feature_names"],
            means=payload["means"],
            scales=payload["scales"],
            direction_weights=payload["direction_weights"],
            return_weights=payload["return_weights"],
            ridge=float(payload.get("ridge", 0.0)),
            model_version=str(payload.get("model_version") or "unknown"),
        )


def _safe_float(value: Any) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _metrics(
    examples: Sequence[dict[str, Any]],
    predictions: Sequence[dict[str, float]],
    *,
    baseline_predictions: Sequence[dict[str, float]] | None = None,
) -> dict[str, Any]:
    if not examples:
        return {
            "samples": 0,
            "direction_accuracy_pct": None,
            "mae_pct": None,
            "active_signals": 0,
            "baseline": None,
        }
    actual_direction = np.asarray([item["target_direction"] for item in examples], dtype=int)
    actual_return = np.asarray([item["target_return"] for item in examples], dtype=float)
    predicted_direction = np.asarray(
        [1 if item["direction_probability"] >= 0.5 else 0 for item in predictions],
        dtype=int,
    )
    predicted_return = np.asarray([item["predicted_return"] for item in predictions], dtype=float)
    result: dict[str, Any] = {
        "samples": len(examples),
        "direction_accuracy_pct": round(float(np.mean(predicted_direction == actual_direction) * 100.0), 6),
        "mae_pct": round(float(np.mean(np.abs(predicted_return - actual_return)) * 100.0), 6),
        "active_signals": sum(item["direction"] != "NEUTRAL" for item in predictions),
        "mean_actual_return_pct": round(float(np.mean(actual_return) * 100.0), 6),
    }
    if baseline_predictions is not None:
        base_direction = np.asarray(
            [1 if item["direction_probability"] >= 0.5 else 0 for item in baseline_predictions],
            dtype=int,
        )
        base_return = np.asarray(
            [item["predicted_return"] for item in baseline_predictions],
            dtype=float,
        )
        result["baseline"] = {
            "direction_accuracy_pct": round(float(np.mean(base_direction == actual_direction) * 100.0), 6),
            "mae_pct": round(float(np.mean(np.abs(base_return - actual_return)) * 100.0), 6),
        }
    return result


def _baseline_predictions(
    examples: Sequence[dict[str, Any]],
    *,
    mode: str = "momentum",
) -> list[dict[str, float]]:
    output: list[dict[str, float]] = []
    for item in examples:
        features = item["features"]
        if mode == "zero":
            probability = 0.5
            predicted_return = 0.0
        else:
            previous = float(features.get("return_1d", 0.0))
            probability = 0.6 if previous > 0 else 0.4 if previous < 0 else 0.5
            predicted_return = previous
        output.append(
            {
                "direction_probability": probability,
                "predicted_return": predicted_return,
                "direction": "UP" if probability >= 0.55 else "DOWN" if probability <= 0.45 else "NEUTRAL",
            }
        )
    return output


def _dataset_digest(examples: Sequence[dict[str, Any]]) -> str:
    encoded = json.dumps(examples, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class LearningMemory:
    """Append-only JSON memory for model runs and realized outcomes."""

    def __init__(self, root: str | Path = "runtime/learning") -> None:
        self.root = Path(root)

    def append(self, symbol: str, record: dict[str, Any], *, run_id: str | None = None) -> str:
        identifier = run_id or str(record.get("run_id") or uuid.uuid4().hex)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(symbol or "UNKNOWN"))
        target = self.root / safe / "runs" / f"{identifier}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Learning artifact already exists: {target}")
        payload = dict(record)
        payload["run_id"] = identifier
        payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # A JSONL index is append-only and convenient for audits.  It is not
        # used as the source of truth if a run artifact is missing.
        index = target.parent.parent / "index.jsonl"
        with index.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"run_id": identifier, "path": os.fspath(target), "decision": payload.get("decision")}, ensure_ascii=False) + "\n")
        return os.fspath(target)

    def append_outcome(self, symbol: str, outcome: dict[str, Any]) -> str:
        payload = dict(outcome)
        payload.setdefault("type", "realized_outcome")
        payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        return self.append(symbol, payload, run_id=f"outcome-{uuid.uuid4().hex}")


class AITrainingService:
    """Train, evaluate and persist a local SMART model."""

    def __init__(
        self,
        *,
        memory: LearningMemory | None = None,
        memory_root: str | Path = "runtime/learning",
    ) -> None:
        self.memory = memory or LearningMemory(memory_root)

    def train(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        symbol: str = "",
        config: TrainingConfig | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        cfg = config or TrainingConfig()
        examples = build_training_dataset(rows, horizon=cfg.horizon, min_history=cfg.min_history)
        started = datetime.now(timezone.utc).isoformat()
        digest = _dataset_digest(examples)
        base_record: dict[str, Any] = {
            "schema_version": "1.0",
            "type": "training_run",
            "symbol": symbol,
            "model_version": cfg.model_version,
            "feature_set_version": cfg.feature_set_version,
            "dataset_sha256": digest,
            "no_lookahead": True,
            "parameters": asdict(cfg),
            "sample_count": len(examples),
            "started_at": started,
        }
        if not examples:
            base_record.update(
                {
                    "status": "INSUFFICIENT_DATA",
                    "decision": "HOLD",
                    "reason": "No valid point-in-time examples were available.",
                }
            )
            path = self.memory.append(symbol, base_record, run_id=run_id)
            base_record["artifact_path"] = path
            return base_record

        train_end = max(1, int(len(examples) * cfg.train_ratio))
        validation_end = max(train_end + 1, int(len(examples) * (cfg.train_ratio + cfg.validation_ratio)))
        validation_end = min(validation_end, len(examples) - 1) if len(examples) > 1 else len(examples)
        train_examples = examples[:train_end]
        validation_examples = examples[train_end:validation_end]
        test_examples = examples[validation_end:]
        # Tiny datasets still produce a useful artifact, but are held back
        # from promotion because the frozen test window is too small.
        if not validation_examples:
            validation_examples = train_examples
        if not test_examples:
            test_examples = validation_examples

        train_features = [item["features"] for item in train_examples]
        train_y_dir = [item["target_direction"] for item in train_examples]
        train_y_ret = [item["target_return"] for item in train_examples]
        validation_baseline = _baseline_predictions(validation_examples)
        candidates: list[dict[str, Any]] = []
        for ridge in cfg.ridge_values:
            model = TrainedLinearModel.fit(
                train_features,
                train_y_dir,
                train_y_ret,
                ridge=float(ridge),
                model_version=cfg.model_version,
            )
            predictions = model.predict([item["features"] for item in validation_examples])
            metrics = _metrics(
                validation_examples,
                predictions,
                baseline_predictions=validation_baseline,
            )
            candidates.append(
                {
                    "ridge": float(ridge),
                    "metrics": metrics,
                    "model": model,
                }
            )
        winner = max(
            candidates,
            key=lambda item: (
                item["metrics"].get("direction_accuracy_pct") or -float("inf"),
                -(item["metrics"].get("mae_pct") or float("inf")),
            ),
        )

        refit_examples = train_examples + validation_examples
        final_model = TrainedLinearModel.fit(
            [item["features"] for item in refit_examples],
            [item["target_direction"] for item in refit_examples],
            [item["target_return"] for item in refit_examples],
            ridge=winner["ridge"],
            model_version=cfg.model_version,
        )
        test_predictions = final_model.predict([item["features"] for item in test_examples])
        test_baseline = _baseline_predictions(test_examples)
        test_metrics = _metrics(test_examples, test_predictions, baseline_predictions=test_baseline)
        validation_metrics = winner["metrics"]
        baseline_val = validation_metrics.get("baseline") or {}
        baseline_test = test_metrics.get("baseline") or {}
        enough_test = len(test_examples) >= max(10, cfg.horizon * 3)
        def _beats(model_metrics: dict[str, Any], baseline_metrics: dict[str, Any]) -> bool:
            model_direction = model_metrics.get("direction_accuracy_pct")
            base_direction = baseline_metrics.get("direction_accuracy_pct")
            model_mae = model_metrics.get("mae_pct")
            base_mae = baseline_metrics.get("mae_pct")
            if None in (model_direction, base_direction, model_mae, base_mae):
                return False
            direction_ok = model_direction >= base_direction
            mae_ok = model_mae <= base_mae
            strict = model_direction > base_direction or model_mae < base_mae
            return direction_ok and mae_ok and strict

        beats_validation = _beats(validation_metrics, baseline_val)
        beats_test = _beats(test_metrics, baseline_test)
        decision = "PROMOTE" if enough_test and beats_validation and beats_test else "REJECT"
        reason = (
            "Model beat the selected baseline on validation and frozen test windows."
            if decision == "PROMOTE"
            else "Model did not demonstrate robust out-of-sample improvement over baseline."
        )

        predictions_artifact = []
        for example, prediction in zip(test_examples, test_predictions):
            predictions_artifact.append(
                {
                    "decision_date": example["decision_date"],
                    "target_date": example["target_date"],
                    "prediction": prediction,
                    "actual_return": example["target_return"],
                    "actual_direction": example["target_direction"],
                }
            )
        record = {
            **base_record,
            "status": "COMPLETE",
            "decision": decision,
            "reason": reason,
            "ranges": {
                "train": [train_examples[0]["decision_date"], train_examples[-1]["target_date"]],
                "validation": [validation_examples[0]["decision_date"], validation_examples[-1]["target_date"]],
                "test": [test_examples[0]["decision_date"], test_examples[-1]["target_date"]],
            },
            "counts": {
                "train": len(train_examples),
                "validation": len(validation_examples),
                "test": len(test_examples),
            },
            "selection": {
                "candidates": [
                    {"ridge": item["ridge"], "metrics": item["metrics"]}
                    for item in candidates
                ],
                "winner_ridge": winner["ridge"],
                "rule": "validation direction accuracy first, MAE second",
            },
            "validation": validation_metrics,
            "test": test_metrics,
            "model_artifact": final_model.as_dict(),
            "predictions": predictions_artifact,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.memory.append(symbol, record, run_id=run_id)
        record["artifact_path"] = path
        return record

    def record_outcome(
        self,
        *,
        symbol: str,
        prediction_id: str,
        decision_date: str,
        horizon: int,
        realized_return: float | None,
        error_class: str | None = None,
        notes: str = "",
    ) -> str:
        """Persist a realized outcome for a prior prediction."""

        outcome = {
            "prediction_id": prediction_id,
            "decision_date": decision_date,
            "horizon": horizon,
            "realized_return": realized_return,
            "correct_direction": (
                None if realized_return is None else realized_return > 0
            ),
            "error_class": error_class,
            "notes": notes,
        }
        return self.memory.append_outcome(symbol, outcome)

    @staticmethod
    def load_model(artifact_path: str | Path) -> TrainedLinearModel:
        """Load the model head from a persisted training-run JSON file."""

        path = Path(artifact_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TrainedLinearModel.from_dict(payload["model_artifact"])

    @staticmethod
    def predict_rows(
        model: TrainedLinearModel,
        rows: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Predict the latest point-in-time feature for each supplied row."""

        ordered = normalize_rows(rows)
        output: list[dict[str, Any]] = []
        for index in range(1, len(ordered) + 1):
            snapshot = feature_snapshot(ordered[:index])
            prediction = model.predict([snapshot])[0]
            output.append(
                {
                    "decision_date": _row_date(ordered[index - 1]).isoformat(),
                    "prediction": prediction,
                    "history_end_index": index - 1,
                }
            )
        return output


__all__ = [
    "AITrainingService",
    "FEATURE_NAMES",
    "LearningMemory",
    "TrainedLinearModel",
    "TrainingConfig",
    "build_training_dataset",
    "feature_snapshot",
    "normalize_rows",
]
