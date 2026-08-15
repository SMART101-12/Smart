"""Local persistent market snapshot storage for SMART.

SQLite is used intentionally: it requires no external database, survives
process restarts, and can later be moved to Postgres without changing the
analysis contracts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MarketStore:
    """Persist every fetched market snapshot and make freshness auditable."""

    def __init__(self, path: str | Path = "data/smart.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshot_symbol_time "
                "ON market_snapshots(symbol, observed_at DESC)"
            )

    def save_snapshot(
        self,
        symbol: str,
        source: str,
        observed_at: datetime,
        payload: dict[str, Any],
    ) -> int:
        """Save raw source data before analysis; return the row id."""
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        saved_at = datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO market_snapshots
                    (symbol, source, observed_at, saved_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    source,
                    observed_at.isoformat(),
                    saved_at.isoformat(),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )
            return int(cur.lastrowid)

    def latest_snapshot(self, symbol: str, source: str | None = None) -> dict[str, Any] | None:
        """Return the newest stored observation for a symbol/source."""
        query = "SELECT * FROM market_snapshots WHERE symbol = ?"
        params: list[Any] = [symbol]
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY observed_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "symbol": row["symbol"],
            "source": row["source"],
            "observed_at": row["observed_at"],
            "saved_at": row["saved_at"],
            "payload": json.loads(row["payload_json"]),
        }

    def history(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent stored observations for audit/comparison."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM market_snapshots WHERE symbol = ? "
                "ORDER BY observed_at DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "source": r["source"],
                "observed_at": r["observed_at"],
                "saved_at": r["saved_at"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in rows
        ]
