"""Fetch full daily TSETMC history for every symbol in the latest MarketWatch universe.

Identity rule:
  - MarketWatch supplies the current symbol universe.
  - TSETMC InsCode is the stable identity used for historical requests.

The job is resumable: successful symbols already stored for today's run are
skipped, while failures are recorded and retried on the next run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import urllib.parse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_DIR = ROOT / "runtime" / "market_raw" / "universe"
OUT = ROOT / "runtime" / "market_raw" / "history"
HISTORY_UNIVERSE = ROOT / "runtime" / "market_raw" / "history_universe"
UA = "Mozilla/5.0 SMART-tsetmc-history-all/1.0"
DELAY = 0.8
RETRIES = 3


def http_get(url: str, timeout: int = 90) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
            with urlopen(req, timeout=timeout) as response:
                data = response.read()
                if not data:
                    raise RuntimeError(f"Empty response: {url}")
                return data
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if attempt < RETRIES:
                time.sleep(attempt * 2)
    raise RuntimeError(f"HTTP request failed after {RETRIES} attempts: {url}; {last_exc}")


def latest_universe() -> Path:
    files = sorted(UNIVERSE_DIR.glob("*.json"), reverse=True)
    if not files:
        raise FileNotFoundError("No MarketWatch universe found in runtime/market_raw/universe")
    return files[0]


def load_symbols(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    symbols: list[str] = []
    for item in payload.get("instruments", []):
        symbol = str(item.get("symbol") or "").strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise RuntimeError(f"No instruments found in {path}")
    return symbols


def find_ins_code(symbol: str) -> tuple[int, str]:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{encoded}"
    data = json.loads(http_get(url).decode("utf-8-sig"))
    rows = data.get("instrumentSearch", [])
    exact = [r for r in rows if str(r.get("lVal18AFC", "")).strip() == symbol]
    candidates = exact or rows
    if not candidates:
        raise RuntimeError("TSETMC symbol search returned no result")
    row = candidates[0]
    return int(row["insCode"]), str(row.get("lVal18AFC", symbol))


def num(value, default=0):
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def parse_records(data: dict, ins_code: int) -> list[dict]:
    records: list[dict] = []
    for row in data.get("closingPriceDaily", []):
        date_value = str(row.get("dEven") or "")
        if not re.fullmatch(r"\d{8}", date_value):
            continue
        records.append({
            "date": date_value,
            "high": num(row.get("priceMax", row.get("pMax"))),
            "low": num(row.get("priceMin", row.get("pMin"))),
            "close": num(row.get("pClosing", row.get("priceClosing", row.get("pc")))),
            "last": num(row.get("pDrCotVal", row.get("last", row.get("pl")))),
            "open": num(row.get("priceFirst", row.get("pf"))),
            "previous_close": num(row.get("priceYesterday", row.get("py"))),
            "value": num(row.get("qTotCap", row.get("tval"))),
            "volume": num(row.get("qTotTran5J", row.get("tvol"))),
            "trades": num(row.get("zTotTran", row.get("tno"))),
            "price_change": row.get("priceChange"),
            "ins_code": ins_code,
        })
    return sorted(records, key=lambda r: r["date"])


def safe_symbol(symbol: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", symbol).rstrip(" .") or "UNKNOWN"


def fetch_history(ins_code: int) -> tuple[dict, list[dict], str]:
    url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{ins_code}/0"
    raw = http_get(url).decode("utf-8-sig", errors="replace")
    data = json.loads(raw)
    records = parse_records(data, ins_code)
    if not records:
        raise RuntimeError(f"No historical rows returned for insCode={ins_code}")
    return data, records, url


def already_done(symbol: str, date: str) -> bool:
    folder = OUT / safe_symbol(symbol)
    return (folder / date).exists() or (folder / f"{date}.json").exists()


def existing_status(symbol: str, date: str) -> dict | None:
    """Return today's prior result so successful work can be resumed."""
    path = HISTORY_UNIVERSE / f"{date}-all-market.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    for item in payload.get("symbols", []):
        if item.get("symbol") == symbol:
            return item
    return None


def save_symbol(symbol: str, resolved: str, ins_code: int, raw_data: dict, records: list[dict], source_url: str, today: str) -> dict:
    folder = OUT / safe_symbol(symbol)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "raw").mkdir(parents=True, exist_ok=True)
    (folder / "raw" / f"{today}.json").write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {
        "source": "TSETMC",
        "source_type": "daily_history",
        "symbol": resolved,
        "requested_symbol": symbol,
        "ins_code": ins_code,
        "source_url": source_url,
        "retrieved_at": dt.datetime.now().astimezone().isoformat(),
        "record_count": len(records),
        "first_date": records[0]["date"],
        "last_date": records[-1]["date"],
        "records": records,
    }
    (folder / f"{today}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "symbol": symbol,
        "resolved_symbol": resolved,
        "ins_code": ins_code,
        "record_count": len(records),
        "first_date": records[0]["date"],
        "last_date": records[-1]["date"],
        "source_url": source_url,
        "status": "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()

    today = dt.date.today().isoformat()
    universe_path = latest_universe()
    symbols = load_symbols(universe_path)
    print(f"Market universe: {universe_path}")
    print(f"Total current instruments: {len(symbols)}")

    report_path = HISTORY_UNIVERSE / f"{today}-all-market.json"
    existing: dict[str, dict] = {}
    if report_path.exists():
        try:
            old = json.loads(report_path.read_text(encoding="utf-8-sig"))
            existing = {
                x["symbol"]: x
                for x in old.get("symbols", [])
                if x.get("status") == "ok"
            }
        except Exception:
            existing = {}

    results: list[dict] = []
    ok_count = error_count = skip_count = 0

    for index, symbol in enumerate(symbols, 1):
        # A successful result is immutable for this run date.  Errors are
        # retried when --retry-errors is supplied; interrupted runs resume
        # from the progress file instead of starting over.
        if symbol in existing and not args.retry_errors:
            results.append(existing[symbol])
            skip_count += 1
            print(f"[{index}/{len(symbols)}] SKIP {symbol}: already successful today")
            continue

        print(f"[{index}/{len(symbols)}] Fetching full history: {symbol}")
        try:
            ins_code, resolved = find_ins_code(symbol)
            time.sleep(DELAY)
            raw_data, records, source_url = fetch_history(ins_code)
            item = save_symbol(symbol, resolved, ins_code, raw_data, records, source_url, today)
            results.append(item)
            ok_count += 1
            print(f"  OK: {len(records)} records, {item['first_date']} -> {item['last_date']}")
        except Exception as exc:
            item = {"symbol": symbol, "status": "error", "error": str(exc)}
            results.append(item)
            error_count += 1
            print(f"  ERROR: {exc}")
        time.sleep(DELAY)

        # Persist progress so an interrupted all-market run can resume safely.
        HISTORY_UNIVERSE.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "source": "TSETMC",
            "source_type": "all_market_daily_history",
            "market_universe_file": str(universe_path.relative_to(ROOT)),
            "retrieved_at": dt.datetime.now().astimezone().isoformat(),
            "instrument_count": len(symbols),
            "completed_ok": sum(1 for x in results if x.get("status") == "ok"),
            "completed_error": sum(1 for x in results if x.get("status") == "error"),
            "symbols": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Completed: OK={ok_count}, errors={error_count}, skipped={skip_count}, total={len(symbols)}")
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
