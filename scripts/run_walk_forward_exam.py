"""Run SMART's 200-strategy walk-forward exam for an archived symbol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smart.strategy_lab import walk_forward_exam


def _rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("daily_history") or payload.get("records") or []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--symbol", default="")
    parser.add_argument("--initial-history", type=int, default=20)
    parser.add_argument("--evaluation-window", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = walk_forward_exam(
        _rows(args.archive),
        symbol=args.symbol or args.archive.stem,
        initial_history=args.initial_history,
        evaluation_window=args.evaluation_window,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({
        "status": result.get("status"),
        "symbol": result.get("symbol"),
        "strategy_count": result.get("strategy_count"),
        "metrics": result.get("metrics"),
        "segments": result.get("segments"),
        "artifact": str(args.output) if args.output else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
