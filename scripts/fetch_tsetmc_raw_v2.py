"""Fetch TSETMC raw data per symbol and per Persian calendar day.

Layout:
  runtime/بورس_خام/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json

The payload from TSETMC is stored unchanged. Symbol normalization is used
only to resolve the requested ticker to the correct instrument record.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from smart.persian_text import normalize_persian_text

BASE = "https://cdn.tsetmc.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 SMART-raw-ingestion/2.0"}
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


def resolve_search_row(symbol: str, rows: list[dict]) -> dict:
    """Resolve only an exact ticker/name after Persian Unicode normalization.

    Never fall back to rows[0]: a search can return rights, options, and other
    instruments before or alongside the primary instrument.
    """
    query = normalize_persian_text(symbol)

    ticker_matches = [
        row for row in rows
        if normalize_persian_text(row.get("lVal18AFC", "")) == query
    ]
    if ticker_matches:
        primary = [row for row in ticker_matches if row.get("flow") in {1, 2} and row.get("insCode")]
        if primary:
            return primary[0]

    name_matches = [
        row for row in rows
        if normalize_persian_text(row.get("lVal30", "")) == query
    ]
    if name_matches:
        primary = [row for row in name_matches if row.get("flow") in {1, 2} and row.get("insCode")]
        if primary:
            return primary[0]

    raise RuntimeError(f"No exact primary TSETMC instrument match for {symbol}")


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    # Compact Gregorian -> Jalali conversion; no external dependency required.
    g_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_days[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def main() -> int:
    symbols = read_symbols()
    now = dt.datetime.now(dt.timezone.utc)
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    month_dir = f"{jy:04d}-{jm:02d}"
    date_file = f"{jy:04d}-{jm:02d}-{jd:02d}.json"

    RAW.mkdir(parents=True, exist_ok=True)
    ok = 0
    failed = 0

    for symbol in symbols:
        try:
            search_text = get_text(ENDPOINTS["search"].format(symbol=quote(symbol)))
            rows = json.loads(search_text).get("instrumentSearch", [])
            if not rows:
                print(f"NOT_FOUND: {symbol}")
                failed += 1
                continue
            instrument = resolve_search_row(symbol, rows)
            ins_code = str(instrument["insCode"])
            payload = {
                "source": "TSETMC",
                "symbol": symbol,
                "ins_code": ins_code,
                "market_date_jalali": f"{jy:04d}-{jm:02d}-{jd:02d}",
                "received_at_utc": now.isoformat(),
                "raw": {
                    "search": json.loads(search_text),
                    "instrument_info": json.loads(get_text(ENDPOINTS["instrument_info"].format(ins_code=ins_code))),
                    "closing_info": json.loads(get_text(ENDPOINTS["closing_info"].format(ins_code=ins_code))),
                    "daily_history": json.loads(get_text(ENDPOINTS["daily_history"].format(ins_code=ins_code))),
                    "client_type": json.loads(get_text(ENDPOINTS["client_type"].format(ins_code=ins_code))),
                },
            }
            out_dir = RAW / symbol / month_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / date_file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"OK: {symbol} -> {out_dir / date_file}")
            ok += 1
        except Exception as exc:
            print(f"ERROR: {symbol}: {exc}")
            failed += 1

    print(f"Finished: ok={ok}, failed={failed}")
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
