"""Persistence and compact public views of immutable symbol profiles."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .archive import safe_symbol
from .atomic_json import write_json
from .analysis_workers import cancellation_checkpoint


def _persist(profile: dict[str, Any], root: str | Path) -> dict[str, Any]:
    symbol = str(profile.get("symbol") or "UNKNOWN")
    directory = Path(root) / safe_symbol(symbol) / "symbol_profiles"
    directory.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    artifact = directory / f"{run_id}.json"
    latest = directory / "latest.json"
    profile["artifact_path"] = str(artifact)
    profile["latest_artifact_path"] = str(latest)
    cancellation_checkpoint()
    write_json(artifact, profile)
    cancellation_checkpoint()
    write_json(latest, profile)
    return profile


def load_latest_symbol_profile(symbol: str, root: str | Path = "runtime/learning") -> dict[str, Any] | None:
    path = Path(root) / safe_symbol(symbol) / "symbol_profiles" / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def summarize_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a small dashboard/ChatGPT-safe view without the full trade trace."""

    if not isinstance(profile, dict):
        return None
    selected = profile.get("selected_model") or {}
    return {
        "status": profile.get("status"),
        "engine_version": profile.get("engine_version"),
        "symbol": profile.get("symbol"),
        "coverage": profile.get("coverage"),
        "protocol": profile.get("protocol"),
        "selected_model": {
            "config": selected.get("config"),
            "validation_metrics": (selected.get("range_metrics") or {}).get("validation"),
            "test_metrics": (selected.get("range_metrics") or {}).get("test"),
            "selection_score": selected.get("selection_score"),
            "selection_status": selected.get("selection_status"),
            "validation_gate": selected.get("validation_gate"),
            "test_gate": selected.get("test_gate"),
        },
        "current_entry": profile.get("current_entry"),
        "indicator_weights": profile.get("indicator_weights"),
        "promotion": profile.get("promotion"),
        "walk_forward": profile.get("walk_forward"),
        "failure_diagnostics": {
            key: value
            for key, value in (profile.get("failure_diagnostics") or {}).items()
            if key not in {"loss_examples", "win_examples"}
        },
        "artifact_path": profile.get("artifact_path"),
    }
