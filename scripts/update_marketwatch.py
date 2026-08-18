"""Download the raw TSETMC MarketWatch response unchanged.

The endpoint can be slow or intermittently stall. This script retries the
request and writes to a temporary file first, so a failed download never
replaces a previously successful raw file.
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0"
HEADERS = {"User-Agent": "Mozilla/5.0 SMART-marketwatch-raw/1.1"}
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "بورس_خام" / "marketwatch"
MAX_ATTEMPTS = 5
TIMEOUT_SECONDS = 120
RETRY_DELAY_SECONDS = 5


def download() -> tuple[bytes, str, int]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"Download attempt {attempt}/{MAX_ATTEMPTS}...")
            req = Request(URL, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
                status = response.status

            if status != 200 or not raw:
                raise RuntimeError(
                    f"TSETMC returned status={status}, size={len(raw)}"
                )

            # The endpoint currently returns gzip-compressed bytes despite the
            # Excel MIME type. Verify the gzip signature before accepting it.
            if raw[:2] != b"\\x1f\\x8b":
                raise RuntimeError(
                    f"Unexpected response format: first bytes={raw[:8].hex()}"
                )

            return raw, content_type, status
        except (TimeoutError, HTTPError, URLError, OSError, RuntimeError) as exc:
            last_error = exc
            print(f"Attempt {attempt} failed: {exc}")
            if attempt < MAX_ATTEMPTS:
                print(f"Waiting {RETRY_DELAY_SECONDS}s before retry...")
                time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(f"TSETMC download failed after {MAX_ATTEMPTS} attempts: {last_error}")


def main() -> int:
    today = dt.datetime.now().date().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{today}.gz"
    temp = OUT / f".{today}.gz.tmp"

    try:
        raw, content_type, status = download()
        temp.write_bytes(raw)
        temp.replace(target)
    except Exception:
        if temp.exists():
            temp.unlink()
        raise

    print(f"OK: {target}")
    print(f"SIZE: {len(raw)} bytes")
    print(f"CONTENT-TYPE: {content_type}")
    print(f"HEADER: {raw[:4].hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
