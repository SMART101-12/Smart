"""Train the local leakage-safe SMART model from an archived symbol history."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart_v2.ai.training import AITrainingService, TrainingConfig


def load_rows(symbol: str, root: Path) -> list[dict]:
    rows = []
    directory = root / symbol
    for path in sorted(directory.glob("*.json")):
        if not path.stem.isdigit():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.extend(payload.get("daily_history") or payload.get("records") or [])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--history-root", default=str(ROOT / "runtime" / "history"))
    parser.add_argument("--memory-root", default=str(ROOT / "runtime" / "learning"))
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--min-history", type=int, default=30)
    args = parser.parse_args()
    rows = load_rows(args.symbol, Path(args.history_root))
    result = AITrainingService(memory_root=args.memory_root).train(
        rows,
        symbol=args.symbol,
        config=TrainingConfig(horizon=args.horizon, min_history=args.min_history),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"COMPLETE", "INSUFFICIENT_DATA"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
