from __future__ import annotations

import json
from pathlib import Path

from smart.meta_ensemble import compare_legacy, evaluate, walk_forward

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "runtime" / "history"
SYMBOLS = ("پالایش", "فولاد")


def load_rows(symbol: str) -> list[dict]:
    rows: dict[str, dict] = {}
    for path in sorted((HISTORY / symbol).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("daily_history", []):
            date = str(row.get("dEven", ""))
            if len(date) == 8 and date.isdigit():
                rows[date] = row
    return [rows[key] for key in sorted(rows)]


def test_meta_ensemble_comparison_palayesh_foulad():
    report = {}
    for symbol in SYMBOLS:
        rows = load_rows(symbol)
        assert len(rows) >= 100, f"{symbol}: insufficient history: {len(rows)}"
        # Keep the validation window large enough to cover many regimes while
        # keeping CI runtime bounded. The stored Git history remains intact.
        validation_rows = rows[-1500:]
        predictions = walk_forward(validation_rows)
        report[symbol] = {"meta": evaluate(predictions), "legacy": compare_legacy(validation_rows)}
        assert report[symbol]["meta"]["predictions"] > 0
        assert report[symbol]["meta"]["signals"] > 0
        assert report[symbol]["meta"]["accuracy"] is not None
        assert report[symbol]["meta"]["brier"] is not None
    print(json.dumps(report, ensure_ascii=False, indent=2))
