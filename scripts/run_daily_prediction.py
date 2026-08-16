from __future__ import annotations

import json
from pathlib import Path

from smart.daily_prediction import load_git_history, run_walk_forward

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "پالایش"
OUT = ROOT / "runtime" / "experiments" / "پالایش" / "daily_prediction_report.json"

rows = load_git_history(ROOT, SYMBOL)
report = run_walk_forward(rows)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
print(f"rows={report['rows']} predictions={report['prediction_count']}")
