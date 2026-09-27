from __future__ import annotations

import json
from pathlib import Path

from smart.daily_prediction import load_git_history, run_walk_forward

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "پالایش"
OUT = ROOT / "runtime" / "experiments" / "پالایش" / "daily_prediction_report.json"
SUMMARY = ROOT / "runtime" / "experiments" / "پالایش" / "daily_prediction_summary.json"

rows = load_git_history(ROOT, SYMBOL)
report = run_walk_forward(rows)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
summary = {
    "engine_version": report["engine_version"],
    "symbol": report["symbol"],
    "rows": report["rows"],
    "first_date": report["first_date"],
    "last_date": report["last_date"],
    "prediction_count": report["prediction_count"],
    "no_lookahead": report["no_lookahead"],
    "metrics": report["metrics"],
    "final_weights": report["final_weights"],
}
SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
