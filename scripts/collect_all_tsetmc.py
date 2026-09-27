from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://cdn.tsetmc.com/api"
MARKET_WATCH = (
    f"{BASE}/ClosingPrice/GetMarketWatch?market=0&paperTypes[0]=1&paperTypes[1]=2&"
    "paperTypes[2]=3&paperTypes[3]=4&paperTypes[4]=5&paperTypes[5]=6&"
    "paperTypes[6]=7&paperTypes[7]=8&paperTypes[8]=9&withBestLimits=false&hEven=0&RefID=0"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}
ROOT = Path("runtime/tsetmc")


def safe_name(symbol: str, ins_code: str) -> str:
    s = (symbol or "").strip()
    s = re.sub(r"[^\w\u0600-\u06ff.-]+", "_", s)
    return s[:80] or ins_code


def get(session: requests.Session, url: str):
    for attempt in range(4):
        try:
            r = session.get(url, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def main() -> None:
    session = requests.Session()
    session.headers.update(HEADERS)

    data = get(session, MARKET_WATCH)
    rows = data.get("marketwatch", [])
    print("MARKETWATCH:", len(rows))

    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "market_watch_all.json").write_text(
        json.dumps(
            {"source": "TSETMC", "collected_at": datetime.now(timezone.utc).isoformat(), "count": len(rows), "data": data},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    seen = set()
    ok = 0
    failed = 0

    for row in rows:
        ins_code = str(row.get("insCode") or row.get("insCode1") or row.get("insCode2") or "").strip()
        symbol = str(row.get("lVal18AFC") or row.get("lVal18") or "").strip()
        if not ins_code or not symbol or ins_code in seen:
            continue
        seen.add(ins_code)

        folder = ROOT / safe_name(symbol, ins_code)
        folder.mkdir(parents=True, exist_ok=True)

        result = {
            "symbol": symbol,
            "instrument_id": ins_code,
            "source": "TSETMC",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "data": {"market_watch": row},
            "errors": [],
        }

        endpoints = {
            "instrument": f"{BASE}/Instrument/GetInstrument/{ins_code}",
            "closing_price": f"{BASE}/ClosingPrice/GetClosingPriceInfo/{ins_code}",
            "client_type": f"{BASE}/ClientType/GetClientType/{ins_code}/1/0",
            "shareholder": f"{BASE}/Shareholder/GetInstrumentShareHolderLast/{ins_code}",
        }

        for name, url in endpoints.items():
            try:
                result["data"][name] = get(session, url)
            except Exception as exc:
                result["errors"].append({"component": name, "error": str(exc)})

        (folder / "tsetmc.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ok += 1
        if ok % 50 == 0:
            print("COLLECTED:", ok)
        time.sleep(0.05)

    summary = {
        "source": "TSETMC",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "marketwatch_rows": len(rows),
        "unique_symbols": len(seen),
        "folders_written": ok,
        "failed": failed,
    }
    (ROOT / "collection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
