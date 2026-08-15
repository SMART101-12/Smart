"""Local SQLite snapshot store with strict market-day freshness checks."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class SnapshotStore:
    def __init__(self, path: str | Path = "data/smart.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    market_date TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(symbol, source, observed_at)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_snap_symbol_date ON market_snapshots(symbol, market_date)")

    def save(self, symbol: str, source: str, observed_at: datetime, payload: dict[str, Any]) -> None:
        observed_at = observed_at.astimezone(timezone.utc)
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO market_snapshots(symbol, source, observed_at, market_date, payload) VALUES (?, ?, ?, ?, ?)",
                (symbol, source, observed_at.isoformat(), observed_at.date().isoformat(), json.dumps(payload, ensure_ascii=False)),
            )

    def latest(self, symbol: str, source: str | None = None) -> dict[str, Any] | None:
        query = "SELECT symbol, source, observed_at, market_date, payload FROM market_snapshots WHERE symbol=?"
        args: list[Any] = [symbol]
        if source:
            query += " AND source=?"
            args.append(source)
        query += " ORDER BY observed_at DESC LIMIT 1"
        with self._connect() as con:
            row = con.execute(query, args).fetchone()
        if not row:
            return None
        return {"symbol": row[0], "source": row[1], "observed_at": row[2], "market_date": row[3], "payload": json.loads(row[4])}

    def is_fresh_for_today(self, symbol: str, source: str, today: date | None = None) -> bool:
        today = today or datetime.now(timezone.utc).date()
        row = self.latest(symbol, source)
        return bool(row and row["market_date"] == today.isoformat())
