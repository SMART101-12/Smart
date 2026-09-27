"""Audit SMART data layers and optionally remove exact derived duplicates.

Default mode is read-only.  Raw evidence under ``runtime/market_raw`` is
never deleted by this script.  ``--apply-derived-cleanup`` only removes
byte-identical files below the explicitly selected derived root.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from smart.archive import audit_archive_root, remove_exact_duplicate_derived_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=str(ROOT / "runtime" / "market_processed" / "canonical"),
        help="derived archive root to audit",
    )
    parser.add_argument("--apply-derived-cleanup", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    audit = audit_archive_root(args.root)
    result = {"audit": audit}
    if args.apply_derived_cleanup:
        result["cleanup"] = remove_exact_duplicate_derived_files(
            args.root, apply=True
        )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    # Windows PowerShell commonly exposes a cp1252 stdout.  Reports are UTF-8
    # by contract, so make console output resilient to Persian symbols too.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(text)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
