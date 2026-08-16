"""Local SQLite store for raw market snapshots and historical daily records."""

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
            con.execute("""
                CREATE TABLE IF NOT EXISTS daily_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    market_date TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    UNIQUE(symbol, source, market_date)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_snap_symbol_date ON market_snapshots(symbol, market_date)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_history_symbol_date ON daily_history(symbol, market_date)")

    def save(self, symbol: str, source: str, observed_at: datetime, payload: dict[str, Any]) -> None:
        observed_at = observed_at.astimezone(timezone.utc)
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO market_snapshots(symbol, source, observed_at, market_date, payload) VALUES (?, ?, ?, ?, ?)",
                (symbol, source, observed_at.isoformat(), observed_at.date().isoformat(), json.dumps(payload, ensure_ascii=False)),
            )

    def save_daily_history(self, symbol: str, source: str, observed_at: datetime, rows: list[dict[str, Any]], date_key: str = "dEven") -> int:
        """Upsert historical daily rows; return the number of valid rows seen.

        TSETMC's daily records are kept verbatim. We normalize only the market-date
        column used for deduplication, accepting ISO dates and common YYYYMMDD values.
        """
        observed_at = observed_at.astimezone(timezone.utc)
        saved = 0
        with self._connect() as con:
            for row in rows:
                raw_date = row.get(date_key) or row.get("date") or row.get("market_date")
                if raw_date is None:
                    continue
                market_date = str(raw_date)
                if len(market_date) == 8 and market_date.isdigit():
                    market_date = f"{market_date[:4]}-{market_date[4:6]}-{market_date[6:]}"
                try:
                    date.fromisoformat(market_date)
                except ValueError:
                    continue
                con.execute(
                    """INSERT INTO daily_history(symbol, source, market_date, payload, observed_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(symbol, source, market_date) DO UPDATE SET
                         payload=excluded.payload, observed_at=excluded.observed_at""",
                    (symbol, source, market_date, json.dumps(row, ensure_ascii=False), observed_at.isoformat()),
                )
                saved += 1
        return saved

    def history(self, symbol: str, source: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT symbol, source, market_date, observed_at, payload FROM daily_history WHERE symbol=?"
        args: list[Any] = [symbol]
        if source:
            query += " AND source=?"
            args.append(source)
        query += " ORDER BY market_date DESC"
        if limit is not None:
            query += " LIMIT ?"
            args.append(limit)
        with self._connect() as con:
            rows = con.execute(query, args).fetchall()
        return [
            {"symbol": r[0], "source": r[1], "market_date": r[2], "observed_at": r[3], "payload": json.loads(r[4])}
            for r in rows
        ]

    def history_coverage(self, symbol: str, source: str | None = None) -> dict[str, Any]:
        rows = self.history(symbol, source)
        dates = [r["market_date"] for r in rows]
        return {
            "rows": len(rows),
            "first_date": min(dates) if dates else None,
            "last_date": max(dates) if dates else None,
        }

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
