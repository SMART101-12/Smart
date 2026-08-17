from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_meta_ensemble_has_enough_history(symbol: str):
    rows = load_rows(symbol)
    assert len(rows) >= 100, f"{symbol}: insufficient history: {len(rows)}"
    predictions = walk_forward(rows)
    metrics = evaluate(predictions)
    baseline = compare_legacy(rows)
    print(json.dumps({"symbol": symbol, "meta": metrics, "legacy": baseline}, ensure_ascii=False))
    assert metrics["predictions"] > 0
    assert metrics["signals"] > 0
    assert metrics["accuracy"] is not None


def test_meta_ensemble_report_is_comparable():
    report = {}
    for symbol in SYMBOLS:
        rows = load_rows(symbol)
        predictions = walk_forward(rows)
        report[symbol] = {"meta": evaluate(predictions), "legacy": compare_legacy(rows)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(report[symbol]["meta"]["brier"] is not None for symbol in SYMBOLS)
