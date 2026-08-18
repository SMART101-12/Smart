"""Split a raw TSETMC MarketWatch workbook into symbol folders.

Input: runtime/market_raw/marketwatch/YYYY-MM-DD.gz
Outputs:
  runtime/market_raw/stocks/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json
  runtime/market_processed/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json
  runtime/market_raw/universe/YYYY-MM-DD.json

insCode is the primary identity. A normal folder uses the symbol name. If two
insCodes have exactly the same symbol, the folder gets __<insCode> appended so
records can never be merged accidentally.

This first stage does not call external TSETMC APIs. It only parses the saved
raw file, preserves every MarketWatch column, and creates deterministic symbol
snapshots. Enrichment/history can be added as a separate stage after validation.
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARKETWATCH_DIR = ROOT / "runtime" / "market_raw" / "marketwatch"
STOCKS_DIR = ROOT / "runtime" / "market_raw" / "stocks"
PROCESSED_DIR = ROOT / "runtime" / "market_processed"
UNIVERSE_DIR = ROOT / "runtime" / "market_raw" / "universe"


def norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("\u200c", "")


def clean_symbol(value: object) -> str:
    symbol = str(value or "").strip().replace("\u200c", "")
    symbol = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", symbol)
    return symbol.rstrip(" .") or "UNKNOWN"


def source_stamp(source: Path) -> tuple[str, str]:
    stamp = source.stem
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        return stamp, stamp[:7]
    now = dt.datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")


def load_marketwatch(raw: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    from openpyxl import load_workbook

    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    first_rows = []
    for _ in range(30):
        try:
            first_rows.append(next(rows))
        except StopIteration:
            break
    if not first_rows:
        return [], []

    header_idx = None
    headers: list[str] = []
    for i, row in enumerate(first_rows):
        candidate = [str(v or "").strip() for v in row]
        normalized = [norm(v).lower() for v in candidate]
        has_code = any("inscode" in v or v in {"کدسهام", "کدسهم"} for v in normalized)
        has_symbol = any("lval18" in v or v in {"نماد", "symbol"} for v in normalized)
        if has_code and has_symbol:
            header_idx = i
            headers = candidate
            break
    if header_idx is None:
        raise RuntimeError("Could not identify MarketWatch header containing symbol and insCode")

    unique_headers: list[str] = []
    counts: dict[str, int] = {}
    for i, value in enumerate(headers):
        key = value or f"column_{i + 1}"
        counts[key] = counts.get(key, 0) + 1
        unique_headers.append(key if counts[key] == 1 else f"{key}__{counts[key]}")

    def column_index(kind: str) -> int:
        for i, header in enumerate(unique_headers):
            h = norm(header).lower()
            if kind == "code" and ("inscode" in h or h in {"کدسهام", "کدسهم"}):
                return i
            if kind == "symbol" and ("lval18" in h or h in {"نماد", "symbol"}):
                return i
        raise RuntimeError(f"Missing required MarketWatch column: {kind}")

    code_idx = column_index("code")
    symbol_idx = column_index("symbol")
    data_rows = first_rows[header_idx + 1 :]
    data_rows.extend(rows)

    instruments: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for row in data_rows:
        if max(code_idx, symbol_idx) >= len(row):
            continue
        ins_code = norm(row[code_idx])
        symbol = str(row[symbol_idx] or "").strip()
        if not ins_code.isdigit() or not symbol or ins_code in seen_codes:
            continue
        seen_codes.add(ins_code)
        raw_row = {unique_headers[i]: row[i] if i < len(row) else None for i in range(len(unique_headers))}
        instruments.append({"ins_code": ins_code, "symbol": symbol, "raw_row": raw_row})

    return unique_headers, instruments


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    files = sorted(MARKETWATCH_DIR.glob("*.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit(f"No raw MarketWatch file found in {MARKETWATCH_DIR}")

    source = files[0]
    date_str, month_str = source_stamp(source)
    print(f"Processing: {source}")
    headers, instruments = load_marketwatch(source.read_bytes())
    if not instruments:
        raise SystemExit("No instruments found in raw MarketWatch")

    ids_by_symbol: dict[str, list[str]] = {}
    for item in instruments:
        ids_by_symbol.setdefault(item["symbol"], []).append(item["ins_code"])

    write_json(UNIVERSE_DIR / f"{date_str}.json", {
        "source_file": str(source.relative_to(ROOT)),
        "source_date": date_str,
        "column_count": len(headers),
        "instrument_count": len(instruments),
        "columns": headers,
        "instruments": [{"symbol": x["symbol"], "ins_code": x["ins_code"]} for x in instruments],
    })

    for item in instruments:
        symbol = item["symbol"]
        ins_code = item["ins_code"]
        folder_symbol = clean_symbol(symbol)
        if len(ids_by_symbol.get(symbol, [])) > 1:
            folder_symbol = f"{folder_symbol}__{ins_code}"

        payload = {
            "source": "TSETMC",
            "source_file": str(source.relative_to(ROOT)),
            "source_date": date_str,
            "symbol": symbol,
            "ins_code": ins_code,
            "folder_symbol": folder_symbol,
            "columns": headers,
            "raw_marketwatch_row": item["raw_row"],
        }
        write_json(STOCKS_DIR / folder_symbol / month_str / f"{date_str}.json", payload)
        write_json(PROCESSED_DIR / folder_symbol / month_str / f"{date_str}.json", {
            "source": "TSETMC",
            "symbol": symbol,
            "ins_code": ins_code,
            "folder_symbol": folder_symbol,
            "source_file": str(source.relative_to(ROOT)),
            "source_date": date_str,
            "marketwatch": item["raw_row"],
        })

    print(f"Universe: {len(instruments)} instruments")
    print(f"Created symbol snapshots: {len(instruments)}")
    print(f"Raw symbol data: {STOCKS_DIR}")
    print(f"Processed data: {PROCESSED_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
