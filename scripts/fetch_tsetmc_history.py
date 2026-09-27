"""Fetch full daily trading history from TSETMC for configured symbols.

MarketWatch is a point-in-time snapshot. This module uses TSETMC's dedicated
ClosingPriceDailyList endpoint so the stored series represents the instrument's
available daily history rather than today's quote.

Outputs:
  runtime/market_raw/history/<symbol>/<YYYY-MM-DD>.json
  runtime/market_raw/history/<symbol>/raw/<YYYY-MM-DD>.json
  runtime/market_raw/history_universe/<YYYY-MM-DD>.json
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
UA = "Mozilla/5.0 SMART-tsetmc-history/2.0"
DELAY = 0.8


def http_get(url: str, timeout: int = 90) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
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


def _num(value, default=0):
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def parse_daily_closing(data: dict, ins_code: int) -> list[dict]:
    rows = data.get("closingPriceDaily", [])
    records: list[dict] = []
    for row in rows:
        date_value = row.get("dEven")
        if date_value is None:
            continue
        date_text = str(date_value)
        if not re.fullmatch(r"\d{8}", date_text):
            continue
        records.append({
            "date": date_text,
            "high": _num(row.get("priceMax", row.get("pMax"))),
            "low": _num(row.get("priceMin", row.get("pMin"))),
            "close": _num(row.get("pClosing", row.get("priceClosing", row.get("pc")))),
            "last": _num(row.get("pDrCotVal", row.get("last", row.get("pl")))),
            "open": _num(row.get("priceFirst", row.get("pf"))),
            "previous_close": _num(row.get("priceYesterday", row.get("py"))),
            "value": _num(row.get("qTotCap", row.get("tval"))),
            "volume": _num(row.get("qTotTran5J", row.get("tvol"))),
            "trades": _num(row.get("zTotTran", row.get("tno"))),
            "price_change": row.get("priceChange"),
            "ins_code": ins_code,
        })
    return records


def fetch_history(ins_code: int) -> tuple[dict, list[dict], str]:
    # Top=0 means all available daily closing-price history on this endpoint.
    url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{ins_code}/0"
    raw = http_get(url).decode("utf-8-sig", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"TSETMC history response was not JSON: {raw[:120]!r}") from exc
    records = parse_daily_closing(data, ins_code)
    if not records:
        raise RuntimeError(f"No historical rows returned for insCode={ins_code}")
    return data, records, url


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
            raw_data, records, source_url = fetch_history(ins_code)
            time.sleep(DELAY)

            folder = OUT / safe_symbol(symbol)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "raw").mkdir(parents=True, exist_ok=True)
            (folder / "raw" / f"{today}.json").write_text(
                json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            payload = {
                "source": "TSETMC",
                "source_type": "daily_history",
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
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
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
            {"source": "TSETMC", "source_type": "daily_history", "retrieved_at": dt.datetime.now().astimezone().isoformat(), "symbols": universe},
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
