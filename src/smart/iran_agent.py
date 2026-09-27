"""Iran-side market data agent.

Runs on a machine that can reach Iranian market sources. It intentionally
keeps networking separate from analysis and persists every successful raw
snapshot with source and observation timestamps.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

from .snapshot_store import SnapshotStore


class IranDataAgent:
    def __init__(self, store: SnapshotStore | None = None, timeout: int = 15) -> None:
        self.store = store or SnapshotStore()
        self.timeout = timeout

    def fetch_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        response = requests.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def collect_url(self, symbol: str, source: str, url: str) -> dict[str, Any]:
        observed_at = datetime.now(timezone.utc)
        payload = self.fetch_json(url, headers={"User-Agent": "SMART-IranDataAgent/0.1"})
        if isinstance(payload, dict):
            payload = {**payload, "requested_symbol": symbol}
        else:
            payload = {"data": payload, "requested_symbol": symbol}
        self.store.save(symbol, source, observed_at, payload)
        return {
            "symbol": symbol,
            "source": source,
            "observed_at": observed_at.isoformat(),
            "market_date": observed_at.date().isoformat(),
            "fresh_for_today": True,
            "payload": payload,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="SMART Iran market data agent")
    parser.add_argument("--symbol", default="عیار")
    parser.add_argument("--source", default="tsetmc")
    parser.add_argument("--url", default=os.getenv("SMART_SOURCE_URL"))
    args = parser.parse_args()
    if not args.url:
        raise SystemExit("Set SMART_SOURCE_URL or pass --url. Use a verified source endpoint; do not invent one.")
    result = IranDataAgent().collect_url(args.symbol, args.source, args.url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
