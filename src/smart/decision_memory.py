"""Append-only decision and realized-outcome memory for the live app."""
from __future__ import annotations

import json
import math
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(value or "UNKNOWN"))


class DecisionMemory:
    def __init__(self, root: str | Path = "runtime/learning") -> None:
        self.root = Path(root)

    def _decision_path(self, symbol: str, decision_id: str) -> Path:
        return self.root / _safe(symbol) / "decisions" / f"{decision_id}.json"

    def record_decision(self, symbol: str, decision: dict[str, Any]) -> dict[str, Any]:
        decision_id = str(decision.get("decision_id") or uuid.uuid4().hex)
        payload = {
            "schema_version": "1.0",
            "decision_id": decision_id,
            "symbol": symbol,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "outcome": None,
        }
        path = self._decision_path(symbol, decision_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["artifact_path"] = str(path)
        return payload

    def record_outcome(
        self,
        symbol: str,
        decision_id: str,
        *,
        realized_return: float | None,
        reason: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        path = self._decision_path(symbol, decision_id)
        if not path.exists():
            raise FileNotFoundError(f"decision not found: {decision_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        prior = payload.get("decision") or {}
        raw_return = realized_return
        if raw_return is not None:
            try:
                raw_return = float(raw_return)
            except (TypeError, ValueError):
                raw_return = None
            if raw_return is not None and not math.isfinite(raw_return):
                raw_return = None
        predicted = str(
            prior.get("prediction")
            or (prior.get("factor_engine") or {}).get("decision")
            or ""
        ).upper()
        predicted_direction = (
            "UP" if predicted in {"UP", "BUY", "LONG", "POSITIVE_WATCH"}
            else "DOWN" if predicted in {"DOWN", "SELL", "SHORT", "NEGATIVE_WATCH"}
            else "NEUTRAL"
        )
        result = (
            "WIN" if raw_return is not None and raw_return > 0
            else "LOSS" if raw_return is not None and raw_return < 0
            else "FLAT"
        )
        if not reason:
            if result == "LOSS":
                reason = (
                    "direction_error"
                    if predicted_direction in {"UP", "DOWN"} and
                    ((predicted_direction == "UP" and raw_return < 0) or
                     (predicted_direction == "DOWN" and raw_return > 0))
                    else "risk_or_execution_review"
                )
            elif result == "WIN":
                reason = "direction_correct"
            else:
                reason = "no_directional_move"
        actual_direction = (
            "UP" if raw_return is not None and raw_return > 0
            else "DOWN" if raw_return is not None and raw_return < 0
            else "FLAT"
        )
        outcome = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "realized_return": raw_return,
            "result": result,
            "reason": reason,
            "notes": notes,
            "failure_analysis": {
                "category": reason,
                "predicted_direction": predicted_direction,
                "actual_direction": actual_direction,
                "return_pct": round(raw_return * 100.0, 6) if raw_return is not None else None,
                "confidence": prior.get("confidence"),
                "indicators": {
                    key: prior.get("indicators", {}).get(key)
                    for key in ("rsi14", "macd", "macd_signal", "sma20", "sma50", "atr14")
                    if isinstance(prior.get("indicators"), dict)
                    and key in prior.get("indicators", {})
                },
            },
        }
        history = payload.setdefault("outcome_history", [])
        if isinstance(history, list):
            history.append(outcome)
        payload["outcome"] = outcome
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        outcome_path = (
            self.root
            / _safe(symbol)
            / "outcomes"
            / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}.json"
        )
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "type": "realized_outcome",
                    "symbol": symbol,
                    "decision_id": decision_id,
                    "outcome": outcome,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload["artifact_path"] = str(path)
        payload["outcome_artifact_path"] = str(outcome_path)
        return payload

    def list_decisions(self, symbol: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Load recent decision artifacts without mutating the memory."""
        root = self.root / _safe(symbol) / "decisions"
        if not root.exists():
            return []
        paths = sorted(
            root.glob("*.json"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        result: list[dict[str, Any]] = []
        for path in paths[: max(1, min(int(limit), 500))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                payload["artifact_path"] = str(path)
                result.append(payload)
        return result

    def summary(self, symbol: str, *, limit: int = 20) -> dict[str, Any]:
        """Return an auditable overview of wins, losses and failure reasons."""
        decisions = self.list_decisions(symbol, limit=max(limit, 500))
        outcomes = [
            item.get("outcome")
            for item in decisions
            if isinstance(item.get("outcome"), dict)
        ]
        by_result = Counter(str(item.get("result") or "UNKNOWN") for item in outcomes)
        by_reason = Counter(str(item.get("reason") or "unspecified") for item in outcomes)
        return {
            "schema_version": "1.0",
            "type": "decision_memory_summary",
            "symbol": symbol,
            "decision_count": len(decisions),
            "outcome_count": len(outcomes),
            "wins": by_result.get("WIN", 0),
            "losses": by_result.get("LOSS", 0),
            "flats": by_result.get("FLAT", 0),
            "win_rate_pct": round(
                by_result.get("WIN", 0)
                / max(1, by_result.get("WIN", 0) + by_result.get("LOSS", 0))
                * 100.0,
                4,
            ) if outcomes else None,
            "outcomes_by_reason": dict(by_reason),
            "recent_decisions": decisions[: max(1, min(int(limit), 100))],
        }

    def settle_from_rows(
        self,
        symbol: str,
        decision_id: str,
        rows: list[dict[str, Any]],
        *,
        horizon: int = 5,
        notes: str = "",
    ) -> dict[str, Any]:
        """Resolve a stored decision against later bars once they exist."""
        path = self._decision_path(symbol, decision_id)
        if not path.exists():
            raise FileNotFoundError(f"decision not found: {decision_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        decision = payload.get("decision") or {}
        target_date = str(decision.get("as_of") or "")
        ordered = []
        for row in rows:
            date = str(row.get("dEven") or row.get("source_date") or row.get("date") or "")
            date = date.replace("-", "").replace("/", "").strip()
            try:
                close = float(
                    row.get(
                        "pClosing",
                        row.get("close", row.get("pDrCotVal", row.get("priceClosing"))),
                    )
                )
            except (TypeError, ValueError):
                continue
            if len(date) == 8 and date.isdigit() and close > 0:
                ordered.append((date, close))
        ordered.sort()
        index = next((i for i, item in enumerate(ordered) if item[0] == target_date), None)
        if index is None or index + horizon >= len(ordered):
            raise ValueError("not enough later bars to settle this decision")
        realized = ordered[index + horizon][1] / ordered[index][1] - 1.0
        return self.record_outcome(
            symbol,
            decision_id,
            realized_return=realized,
            reason="",
            notes=notes or f"settled automatically at {ordered[index + horizon][0]}",
        )
