"""Download the raw TSETMC MarketWatch response unchanged.

This script intentionally does NOT parse, decompress, normalize, or analyze the
response. The exact bytes returned by TSETMC are saved for later processing.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0"
HEADERS = {"User-Agent": "Mozilla/5.0 SMART-marketwatch-raw/1.0"}
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "market_raw" / "marketwatch"


def main() -> int:
    today = dt.datetime.now().date().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{today}.gz"

    req = Request(URL, headers=HEADERS)
    with urlopen(req, timeout=45) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        status = response.status

    if status != 200 or not raw:
        raise RuntimeError(f"TSETMC download failed: status={status}, size={len(raw)}")

    # MarketWatch currently arrives gzip-compressed despite the Excel MIME type.
    # Keep the bytes exactly as received; do not decompress them here.
    target.write_bytes(raw)
    print(f"OK: {target}")
    print(f"SIZE: {len(raw)} bytes")
    print(f"CONTENT-TYPE: {content_type}")
    print(f"HEADER: {raw[:4].hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


