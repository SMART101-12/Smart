"""Freeze configurable evidence weights into each analysis snapshot."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .final_decision import WEIGHTS as DECISION_WEIGHTS
from .technical_structure import WEIGHTS as TECHNICAL_WEIGHTS
from smart_v2.analysis.trade_policy import TradePolicy


def load_analysis_configuration() -> dict:
    default = {"version": "ANALYSIS-CONFIG-1", "technical_weights": TECHNICAL_WEIGHTS.copy(),
               "decision_weights": DECISION_WEIGHTS.copy()}
    path = Path(os.getenv("SMART_ANALYSIS_CONFIG", "config/analysis_engine.json"))
    if path.exists():
        default = json.loads(path.read_text(encoding="utf-8"))
    elif os.getenv("SMART_ANALYSIS_CONFIG"):
        raise ValueError("Explicit analysis configuration file not found")
    if not isinstance(default, dict) or not isinstance(default.get("version"), str):
        raise ValueError("Analysis configuration requires a version")
    for key, expected in (("technical_weights", TECHNICAL_WEIGHTS), ("decision_weights", DECISION_WEIGHTS)):
        weights = default.get(key)
        if (not isinstance(weights, dict) or set(weights) != set(expected) or
                any(type(v) is not int or v < 0 for v in weights.values()) or sum(weights.values()) != 100):
            raise ValueError(f"Invalid {key}; weights must sum to 100")
    policy = default.get("trade_policy", {})
    if not isinstance(policy, dict):
        raise ValueError("trade_policy must be an object")
    try:
        default["trade_policy"] = TradePolicy(**policy).as_dict()
    except TypeError as exc:
        raise ValueError("Unknown trade policy field") from exc
    encoded = json.dumps(default, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {**default, "sha256": hashlib.sha256(encoded).hexdigest()}
