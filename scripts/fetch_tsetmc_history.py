"""Fetch full daily trading history from TSETMC for configured symbols.

This is the historical-data stage of SMART. It is intentionally separate from
MarketWatch, which is only a point-in-time market snapshot.

Sources:
  - TSETMC symbol search: cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{symbol}
  - TSETMC legacy daily history: old.tsetmc.com/tsev2/data/InstTradeHistory.aspx
  - TSETMC chart history fallback: members.tsetmc.com/tsev2/chart/data/Financial.aspx

Outputs:
  runtime/market_raw/history/<symbol>/YYYY-MM-DD.json
  runtime/market_raw/history/<symbol>/raw/<YYYY-MM-DD>.txt
  runtime/market_raw/history_universe/<YYYY-MM-DD>.json

The raw response is preserved before parsing. No external market-data source is
used for the historical price series.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.parse
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SYMBOL_FILE = ROOT / "config" / "tsetmc_symbols.txt"
OUT = ROOT / "runtime" / "market_raw" / "history"
UNIVERSE = ROOT / "runtime" / "market_raw" / "history_universe"
UA = "Mozilla/5.0 SMART-tsetmc-history/1.0"
DELAY = 0.8


def http_get(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as response:
        data = response.read()
        if not data:
            raise RuntimeError(f"Empty response: {url}")
        return data


def load_symbols() -> list[str]:
    symbols = []
    for line in SYMBOL_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            symbols.append(line)
    return symbols


def find_ins_code(symbol: str) -> tuple[int, str]:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{encoded}"
    data = json.loads(http_get(url).decode("utf-8-sig"))
    rows = data.get("instrumentSearch", [])
    exact = [r for r in rows if str(r.get("lVal18AFC", "")).strip() == symbol]
    candidates = exact or rows
    if not candidates:
        raise RuntimeError(f"TSETMC symbol search returned no result: {symbol}")
    code = int(candidates[0]["insCode"])
    return code, str(candidates[0].get("lVal18AFC", symbol))


def parse_history(text: str, ins_code: int) -> list[dict]:
    # Legacy InstTradeHistory format is rows separated by ';' and fields by ','.
    # Expected fields: date,pmax,pmin,pc,pl,pf,py,tval,tvol,tno.
    records: list[dict] = []
    for row in text.replace("\r", "").split(";"):
        row = row.strip()
        if not row:
            continue
        fields = [x.strip() for x in row.split(",")]
        if len(fields) < 10 or not re.fullmatch(r"\d{8}", fields[0]):
            continue
        try:
            records.append({
                "date": fields[0],
                "high": int(float(fields[1] or 0)),
                "low": int(float(fields[2] or 0)),
                "close": int(float(fields[3] or 0)),
                "last": int(float(fields[4] or 0)),
                "open": int(float(fields[5] or 0)),
                "previous_close": int(float(fields[6] or 0)),
                "value": int(float(fields[7] or 0)),
                "volume": int(float(fields[8] or 0)),
                "trades": int(float(fields[9] or 0)),
                "ins_code": ins_code,
            })
        except ValueError:
            continue
    return records


def fetch_history(ins_code: int) -> tuple[str, list[dict], str]:
    # A very high Top requests the complete available legacy history.
    url = (
        "https://old.tsetmc.com/tsev2/data/InstTradeHistory.aspx"
        f"?i={ins_code}&Top=99999&A=0"
    )
    raw = http_get(url).decode("utf-8-sig", errors="replace")
    records = parse_history(raw, ins_code)
    if records:
        return raw, records, url

    # Fallback to the chart endpoint. It provides a compact daily OHLCV series.
    fallback = (
        "https://members.tsetmc.com/tsev2/chart/data/Financial.aspx"
        f"?i={ins_code}&t=ph&a=0"
    )
    raw2 = http_get(fallback).decode("utf-8-sig", errors="replace")
    records2 = []
    for row in raw2.replace("\r", "").split(";"):
        fields = [x.strip() for x in row.split(",")]
        if len(fields) < 7 or not re.fullmatch(r"\d{8}", fields[0]):
            continue
        try:
            records2.append({
                "date": fields[0],
                "high": int(float(fields[1] or 0)),
                "low": int(float(fields[2] or 0)),
                "open": int(float(fields[3] or 0)),
                "last": int(float(fields[4] or 0)),
                "volume": int(float(fields[5] or 0)),
                "close": int(float(fields[6] or 0)),
                "ins_code": ins_code,
            })
        except ValueError:
            continue
    if not records2:
        raise RuntimeError(f"No historical rows returned for insCode={ins_code}")
    return raw2, records2, fallback


def safe_symbol(symbol: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", symbol).rstrip(" .") or "UNKNOWN"


def main() -> int:
    today = dt.date.today().isoformat()
    symbols = load_symbols()
    if not symbols:
        raise SystemExit("No symbols configured in config/tsetmc_symbols.txt")

    universe = []
    for index, symbol in enumerate(symbols, 1):
        print(f"[{index}/{len(symbols)}] Fetching full history: {symbol}")
        try:
            ins_code, resolved_symbol = find_ins_code(symbol)
            time.sleep(DELAY)
            raw, records, source_url = fetch_history(ins_code)
            time.sleep(DELAY)

            folder = OUT / safe_symbol(symbol)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "raw").mkdir(parents=True, exist_ok=True)
            (folder / "raw" / f"{today}.txt").write_text(raw, encoding="utf-8")
            payload = {
                "source": "TSETMC",
                "symbol": resolved_symbol,
                "requested_symbol": symbol,
                "ins_code": ins_code,
                "source_url": source_url,
                "retrieved_at": dt.datetime.now().astimezone().isoformat(),
                "record_count": len(records),
                "first_date": min(r["date"] for r in records),
                "last_date": max(r["date"] for r in records),
                "records": sorted(records, key=lambda r: r["date"]),
            }
            (folder / f"{today}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            universe.append({
                "symbol": symbol,
                "resolved_symbol": resolved_symbol,
                "ins_code": ins_code,
                "record_count": len(records),
                "first_date": payload["first_date"],
                "last_date": payload["last_date"],
                "source_url": source_url,
                "status": "ok",
            })
            print(f"  OK: {len(records)} rows, {payload['first_date']} -> {payload['last_date']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            universe.append({"symbol": symbol, "status": "error", "error": str(exc)})

    UNIVERSE.mkdir(parents=True, exist_ok=True)
    (UNIVERSE / f"{today}.json").write_text(
        json.dumps(
            {"source": "TSETMC", "retrieved_at": dt.datetime.now().astimezone().isoformat(), "symbols": universe},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    errors = [x for x in universe if x["status"] != "ok"]
    print(f"Completed: {len(universe) - len(errors)}/{len(universe)} symbols")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
