"""Fetch TSETMC responses and store them unchanged in the raw layer.

Data path is intentionally one-way:
TSETMC -> runtime/بورس_خام
No analysis or normalization belongs in this script.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://cdn.tsetmc.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 SMART-raw-ingestion/1.0"}
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "runtime" / "بورس_خام"
SYMBOLS_FILE = ROOT / "config" / "tsetmc_symbols.txt"

ENDPOINTS = {
    "search": "/Instrument/GetInstrumentSearch/{symbol}",
    "instrument_info": "/Instrument/GetInstrumentInfo/{ins_code}",
    "closing_info": "/ClosingPrice/GetClosingPriceInfo/{ins_code}",
    "daily_history": "/ClosingPrice/GetClosingPriceDailyList/{ins_code}/60",
    "client_type": "/ClientType/GetClientType/{ins_code}/1/0",
}


def get_text(path: str) -> str:
    req = Request(BASE + path, headers=HEADERS)
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def read_symbols() -> list[str]:
    if not SYMBOLS_FILE.exists():
        raise SystemExit(f"Missing {SYMBOLS_FILE}")
    return [x.strip() for x in SYMBOLS_FILE.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]


def main() -> int:
    symbols = read_symbols()
    received_at = dt.datetime.now(dt.timezone.utc)
    batch = received_at.strftime("%Y%m%dT%H%M%SZ")
    batch_dir = RAW / batch
    batch_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for symbol in symbols:
        search_text = get_text(ENDPOINTS["search"].format(symbol=quote(symbol)))
        import json
        rows = json.loads(search_text).get("instrumentSearch", [])
        if not rows:
            manifest.append({"symbol": symbol, "status": "not_found"})
            continue
        ins_code = str(rows[0].get("insCode"))
        symbol_dir = batch_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        raw_requests = {
            "search.json": search_text,
            "instrument_info.json": get_text(ENDPOINTS["instrument_info"].format(ins_code=ins_code)),
            "closing_info.json": get_text(ENDPOINTS["closing_info"].format(ins_code=ins_code)),
            "daily_history.json": get_text(ENDPOINTS["daily_history"].format(ins_code=ins_code)),
            "client_type.json": get_text(ENDPOINTS["client_type"].format(ins_code=ins_code)),
        }
        for filename, content in raw_requests.items():
            (symbol_dir / filename).write_text(content, encoding="utf-8")
        manifest.append({"symbol": symbol, "ins_code": ins_code, "status": "ok"})

    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "source": "TSETMC",
            "received_at_utc": received_at.isoformat(),
            "batch": batch,
            "symbols": manifest,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Raw TSETMC batch written to {batch_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
