"""Split the raw TSETMC MarketWatch Excel export into symbol folders.

Input:
  runtime/market_raw/marketwatch/YYYY-MM-DD.gz

The legacy MarketWatchPlus Excel export does NOT contain InsCode. It contains
market-watch fields such as symbol, name, volume, value, prices and order-book
level 1. Therefore this stage uses the symbol as the folder identity and does
not invent an InsCode. InsCode/ISIN enrichment belongs to a later stage.

Outputs:
  runtime/market_raw/stocks/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json
  runtime/market_processed/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json
  runtime/market_raw/universe/YYYY-MM-DD.json
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
    text = str(value or "")
    return re.sub(r"\s+", "", text).replace("\u200c", "").lower()


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


def is_symbol_header(value: object) -> bool:
    h = norm(value)
    return h in {"نماد", "symbol", "lval18", "l18", "lval18afc"} or "نماد" in h


def load_marketwatch(raw: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    from openpyxl import load_workbook

    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    first_rows: list[tuple[Any, ...]] = []
    for _ in range(50):
        try:
            first_rows.append(next(rows))
        except StopIteration:
            break
    if not first_rows:
        return [], []

    # MarketWatchPlus normally has a title/header area before the data header.
    # Do not require InsCode: the Excel export does not provide it.
    header_idx = None
    headers: list[str] = []
    for i, row in enumerate(first_rows):
        candidate = [str(v or "").strip() for v in row]
        symbol_positions = [j for j, v in enumerate(candidate) if is_symbol_header(v)]
        nonempty = sum(1 for v in candidate if v)
        if symbol_positions and nonempty >= 5:
            header_idx = i
            headers = candidate
            break

    if header_idx is None:
        raise RuntimeError(
            "Could not identify MarketWatch Excel header containing the symbol column"
        )

    unique_headers: list[str] = []
    counts: dict[str, int] = {}
    for i, value in enumerate(headers):
        key = value or f"column_{i + 1}"
        counts[key] = counts.get(key, 0) + 1
        unique_headers.append(key if counts[key] == 1 else f"{key}__{counts[key]}")

    symbol_idx = next(
        i for i, header in enumerate(unique_headers) if is_symbol_header(header)
    )

    data_rows = first_rows[header_idx + 1 :]
    data_rows.extend(rows)

    instruments: list[dict[str, Any]] = []
    seen_rows = set()
    for row_number, row in enumerate(data_rows, start=header_idx + 2):
        if symbol_idx >= len(row):
            continue
        symbol = str(row[symbol_idx] or "").strip().replace("\u200c", "")
        if not symbol:
            continue

        raw_row = {
            unique_headers[i]: row[i] if i < len(row) else None
            for i in range(len(unique_headers))
        }
        # Avoid repeated title/header rows or completely empty rows.
        fingerprint = json.dumps(raw_row, ensure_ascii=False, default=str, sort_keys=True)
        if fingerprint in seen_rows:
            continue
        seen_rows.add(fingerprint)
        instruments.append({
            "symbol": symbol,
            "row_number": row_number,
            "raw_row": raw_row,
        })

    return unique_headers, instruments


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> int:
    files = sorted(
        MARKETWATCH_DIR.glob("*.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise SystemExit(f"No raw MarketWatch file found in {MARKETWATCH_DIR}")

    source = files[0]
    date_str, month_str = source_stamp(source)
    print(f"Processing: {source}")
    headers, instruments = load_marketwatch(source.read_bytes())
    if not instruments:
        raise SystemExit("No instruments found in raw MarketWatch")

    # Keep duplicate symbols separate instead of silently merging them.
    symbol_counts: dict[str, int] = {}
    for item in instruments:
        symbol_counts[item["symbol"]] = symbol_counts.get(item["symbol"], 0) + 1
    symbol_seen: dict[str, int] = {}

    universe_items = []
    for item in instruments:
        symbol = item["symbol"]
        folder_symbol = clean_symbol(symbol)
        symbol_seen[symbol] = symbol_seen.get(symbol, 0) + 1
        if symbol_counts[symbol] > 1:
            folder_symbol = f"{folder_symbol}__{symbol_seen[symbol]}"

        payload = {
            "source": "TSETMC",
            "source_file": str(source.relative_to(ROOT)),
            "source_date": date_str,
            "symbol": symbol,
            "folder_symbol": folder_symbol,
            "ins_code": None,
            "columns": headers,
            "raw_marketwatch_row": item["raw_row"],
        }
        write_json(
            STOCKS_DIR / folder_symbol / month_str / f"{date_str}.json",
            payload,
        )
        write_json(
            PROCESSED_DIR / folder_symbol / month_str / f"{date_str}.json",
            {
                "source": "TSETMC",
                "symbol": symbol,
                "folder_symbol": folder_symbol,
                "ins_code": None,
                "source_file": str(source.relative_to(ROOT)),
                "source_date": date_str,
                "marketwatch": item["raw_row"],
            },
        )
        universe_items.append({
            "symbol": symbol,
            "folder_symbol": folder_symbol,
            "ins_code": None,
            "row_number": item["row_number"],
        })

    write_json(
        UNIVERSE_DIR / f"{date_str}.json",
        {
            "source_file": str(source.relative_to(ROOT)),
            "source_date": date_str,
            "column_count": len(headers),
            "instrument_count": len(instruments),
            "columns": headers,
            "ins_code_available_in_source": False,
            "instruments": universe_items,
        },
    )

    print(f"Universe: {len(instruments)} rows")
    print(f"Created symbol snapshots: {len(instruments)}")
    print(f"Raw symbol data: {STOCKS_DIR}")
    print(f"Processed data: {PROCESSED_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
