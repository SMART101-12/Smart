"""Separate, immutable forward observations and research-only learning candidates."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from .archive import deduplicate_rows
from .final_decision import VERSION, decide


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def replay_decision(summary: dict[str, Any]) -> dict[str, Any]:
    recorded = summary.get("decision") or {}
    from .final_decision import SUPPORTED_VERSIONS
    if recorded.get("version") not in SUPPORTED_VERSIONS:
        raise ValueError("Replay requires the recorded decision engine version")
    replay = decide(summary, weights=recorded["weights"], version=recorded["version"])
    return {"analysis_id": summary["analysis_id"], "version": recorded["version"],
            "matches": replay == recorded, "recorded_sha256": _digest(recorded),
            "replayed_sha256": _digest(replay), "decision": replay}


def record_forward_outcomes(summary: dict[str, Any], history: list[dict[str, Any]],
                            directory: Path, *, as_of: date) -> list[dict[str, Any]]:
    """Observe 1/5/10 future sessions; these are price outcomes, not trade P&L."""
    anchor = (summary.get("quality_gate") or {}).get("latest_valid_date")
    if not anchor:
        return []
    rows, _ = deduplicate_rows(history, symbol=summary["requested_symbol"])
    rows = [r for r in rows if r["source_date"] <= as_of.isoformat()]
    index = next((i for i, r in enumerate(rows) if r["source_date"] == anchor), None)
    if index is None:
        return []
    base = (summary.get("technical_structure") or {}).get("timeframes", {}).get("daily", {}).get("last_close")
    if type(base) not in (int, float) or base <= 0:
        return []
    if rows[index].get("close") != base:
        # Later source corrections/adjustments cannot silently alter the
        # original decision's price basis.
        return []
    recorded = []
    for horizon in (1, 5, 10):
        if index + horizon >= len(rows):
            continue
        future = rows[index + 1:index + horizon + 1]
        if any(any(type(r.get(k)) not in (int, float) or r[k] <= 0
                   for k in ("open", "high", "low", "close")) or
               not r["low"] <= min(r["open"], r["close"]) <= max(r["open"], r["close"]) <= r["high"]
               for r in future):
            continue
        source_hash = _digest([rows[index], *future])
        payload = {"schema_version": "ANALYSIS-OUTCOME-1", "analysis_id": summary["analysis_id"],
                   "symbol": summary["requested_symbol"], "decision_version": (summary.get("decision") or {}).get("version"),
                   "decision_sha256": _digest(summary.get("decision")),
                   "setup_state": (summary.get("setup") or {}).get("state"),
                   "failed_gates": (summary.get("decision") or {}).get("failed_gates", []),
                   "horizon_sessions": horizon, "anchor_date": anchor,
                   "end_date": future[-1]["source_date"], "source": "TSETMC",
                   "source_data_sha256": source_hash,
                   "forward_close_return_pct": round(100 * (future[-1]["close"] / base - 1), 6),
                   "mfe_pct": round(max(0., 100 * (max(r["high"] for r in future) / base - 1)), 6),
                   "mae_pct": round(min(0., 100 * (min(r["low"] for r in future) / base - 1)), 6),
                   "is_executed_trade_return": False}
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{horizon}-{source_hash}.json"
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError("Existing outcome artifact integrity conflict")
        recorded.append(payload)
    return recorded


def learning_candidate(outcomes: list[dict[str, Any]], *, minimum_samples: int = 30) -> dict[str, Any]:
    """A descriptive research proposal never changes production parameters."""
    if minimum_samples < 30:
        raise ValueError("Learning research requires at least 30 independent analyses")
    # Corrected source revisions do not create independent extra samples.
    unique = {r["analysis_id"]: r for r in outcomes if r.get("horizon_sessions") == 10}
    values = list(unique.values())
    result = {"version": "LEARNING-CANDIDATE-1", "production_active": False,
              "sample_count": len(values), "minimum_samples": minimum_samples,
              "dataset_sha256": _digest(sorted(values, key=lambda r: r["analysis_id"])),
              "required_before_promotion": ["independent_train_validation_frozen_test",
                                            "human_review", "approved_model_version"],
              "status": "INSUFFICIENT_DATA", "proposal": None}
    if len(values) >= minimum_samples:
        result.update(status="RESEARCH_CANDIDATE", proposal={
            "kind": "review_setup_and_failed_gate_patterns",
            "mean_observed_10_session_return_pct": round(mean(r["forward_close_return_pct"] for r in values), 6),
            "performance_is_not_strategy_profit": True})
    return result
