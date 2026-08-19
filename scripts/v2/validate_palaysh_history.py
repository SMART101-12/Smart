from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from smart.history_quality import audit_symbol, load_symbol_rows
from smart_v2.validation.runner import validate_symbol_payload

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "پالایش"
INS_CODE = "67675656072510693"
OUT = ROOT / "runtime" / "validation_reports" / "PALAYESH_67675656072510693"


def main() -> int:
    rows = load_symbol_rows(SYMBOL)
    if not rows:
        raise SystemExit("No PALAYESH history found in runtime/history/پالایش")

    quality = audit_symbol(SYMBOL, market_type="EQUITY")
    payload = {
        "requested_symbol": "PALAYESH",
        "ins_code": INS_CODE,
        "daily_history": list(rows.values()),
    }
    result = validate_symbol_payload(payload)

    report = {
        "schema_version": "2.0",
        "run_id": f"PALAYESH-VALIDATION-{date.today().isoformat()}",
        "symbol": "PALAYESH",
        "ins_code": INS_CODE,
        "record_validation": result.as_dict(),
        "history_quality": quality,
        "source": "runtime/history/پالایش",
        "status": "PASS" if result.status == "PASS" and not quality.get("missing_expected") else "FAIL",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
