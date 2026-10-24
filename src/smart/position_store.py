"""Durable, user-reported positions and idempotent exit observations.

No orders are sent. Paper fills and reported real fills are explicitly distinct.
SQLite transactions serialize quantity changes; immutable events retain inputs.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .archive import deduplicate_rows
from .financial_history import normalize
from .position_review import review_position
from .risk import _finite_nonnegative, _finite_positive
from smart_v2.analysis.trade_policy import TradePolicy


def _encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Tehran")).date()


class PositionStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("SMART_POSITIONS_DB") or
                         Path(os.getenv("SMART_DATA_ROOT", "data")) / "positions.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS position_events (
                    request_id TEXT PRIMARY KEY, position_id TEXT NOT NULL,
                    input TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS position_reviews (
                    id TEXT PRIMARY KEY, position_id TEXT NOT NULL,
                    payload TEXT NOT NULL);
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=15)

    @staticmethod
    def _request_id(value: str) -> None:
        if not isinstance(value, str) or not 8 <= len(value) <= 128:
            raise ValueError("request_id must contain 8 to 128 characters")

    @staticmethod
    def _existing(con: sqlite3.Connection, request_id: str, payload: str) -> dict[str, Any] | None:
        row = con.execute("SELECT input,result FROM position_events WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row[0] != payload:
            raise ValueError("request_id already used with different inputs")
        return json.loads(row[1])

    @staticmethod
    def _save_event(con: sqlite3.Connection, request_id: str, payload: str, position: dict[str, Any]) -> None:
        con.execute("INSERT INTO position_events VALUES(?,?,?,?)",
                    (request_id, position["id"], payload, _encoded(position)))
        con.execute("INSERT INTO positions VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (position["id"], _encoded(position)))

    def open(self, *, request_id: str, symbol: str, mode: str, entry_date: date,
             entry_price: float, quantity: int, stop: float, tp1: float, tp2: float,
             entry_fee: float = 0, policy: TradePolicy | None = None) -> dict[str, Any]:
        self._request_id(request_id)
        symbol = normalize(symbol)
        if not symbol or len(symbol) > 80 or any(ord(c) < 32 for c in symbol):
            raise ValueError("Invalid symbol")
        if mode not in {"PAPER", "REPORTED_REAL"} or entry_date > _today():
            raise ValueError("Explicit position mode and nonfuture entry date required")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")
        for key, value in (("entry", entry_price), ("stop", stop), ("tp1", tp1), ("tp2", tp2)):
            _finite_positive(value, key)
        _finite_nonnegative(entry_fee, "entry_fee")
        if not stop < entry_price < tp1 < tp2:
            raise ValueError("Required: stop < entry < TP1 < TP2")
        policy = policy or TradePolicy()
        inputs = dict(kind="OPEN", symbol=symbol, mode=mode, entry_date=entry_date.isoformat(),
                      entry_price=entry_price, quantity=quantity, stop=stop, tp1=tp1, tp2=tp2,
                      entry_fee=entry_fee)
        payload = _encoded(inputs)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = self._existing(con, request_id, payload)
            if prior is not None:
                return prior
            position = {**inputs, "id": uuid.uuid4().hex, "status": "OPEN",
                        "remaining_quantity": quantity, "realized_net_pnl": 0.0,
                        "policy": policy.as_dict(), "fills": [], "stop_changes": [],
                        "fill_verification": "USER_REPORTED", "orders_submitted": False}
            self._save_event(con, request_id, payload, position)
            return position

    def get(self, position_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT payload FROM positions WHERE id=?", (position_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("Position not found")
            result = json.loads(row[0])
            result["reviews"] = [json.loads(r[0]) for r in con.execute(
                "SELECT payload FROM position_reviews WHERE position_id=? ORDER BY rowid DESC LIMIT 30", (position_id,))]
            return result

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [json.loads(row[0]) for row in con.execute("SELECT payload FROM positions ORDER BY rowid DESC")]

    def exit_fill(self, position_id: str, *, request_id: str, fill_date: date,
                  price: float, quantity: int, fee: float = 0,
                  reason: str = "MANUAL") -> dict[str, Any]:
        self._request_id(request_id)
        _finite_positive(price, "price")
        _finite_nonnegative(fee, "fee")
        if type(quantity) is not int or quantity <= 0 or reason not in {"MANUAL", "TP1", "TP2", "STOP", "TIME"}:
            raise ValueError("Invalid reported exit")
        inputs = dict(kind="EXIT", position_id=position_id, date=fill_date.isoformat(),
                      price=price, quantity=quantity, fee=fee, reason=reason)
        payload = _encoded(inputs)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = self._existing(con, request_id, payload)
            if prior is not None:
                return prior
            row = con.execute("SELECT payload FROM positions WHERE id=?", (position_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("Position not found")
            position = json.loads(row[0])
            last = position["fills"][-1]["date"] if position["fills"] else position["entry_date"]
            if fill_date.isoformat() < last or fill_date > _today() or quantity > position["remaining_quantity"]:
                raise ValueError("Exit date or quantity conflicts with current position")
            pnl = quantity * (price - position["entry_price"]) - fee - position["entry_fee"] * quantity / position["quantity"]
            position["fills"].append({**inputs, "net_pnl": pnl})
            position["remaining_quantity"] -= quantity
            position["realized_net_pnl"] += pnl
            position["status"] = "CLOSED" if position["remaining_quantity"] == 0 else "PARTIAL_EXIT"
            self._save_event(con, request_id, payload, position)
            return position

    def review(self, position_id: str, history: list[dict[str, Any]], *, as_of: date) -> dict[str, Any]:
        """Review completed observed sessions, never silently skip a bad candle.

        Entry-session OHLC is not used: exact fill time is not recorded here.
        Time exit counts observed sessions only; calendar continuity is unknown.
        """
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT payload FROM positions WHERE id=?", (position_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("Position not found")
            position = json.loads(row[0])
            if as_of >= _today():
                raise ValueError("Review requires a completed day before today")
            if position["status"] == "CLOSED":
                raise ValueError("Position is closed")
            rows, audit = deduplicate_rows(history, symbol=position["symbol"])
            rows = [r for r in rows if position["entry_date"] < r["source_date"] <= as_of.isoformat()]
            result: dict[str, Any] = {"position_id": position_id, "as_of": as_of.isoformat(),
                "status": "insufficient_data", "action": "REVIEW_DATA", "observations": [],
                "calendar_continuity": "UNVERIFIED", "orders_submitted": False,
                "reason": "Missing, duplicate, invalid or stale history"}
            if rows and rows[-1]["source_date"] == as_of.isoformat() and not audit["invalid_rows"] and not audit["duplicate_dates"]:
                observations = []
                for i, candle in enumerate(rows, 1):
                    # Only sales known strictly before the session can affect it.
                    earlier = [f for f in position["fills"] if f["date"] < candle["source_date"]]
                    seen_tp1 = any(f["reason"] == "TP1" for f in earlier)
                    active_stop = position["stop"]
                    for change in position["stop_changes"]:
                        if change["effective_on"] <= candle["source_date"]:
                            active_stop = change["stop"]
                    review = review_position(entry_price=position["entry_price"], stop=active_stop,
                        tp1=position["tp1"], tp2=position["tp2"], bar=candle,
                        as_of=date.fromisoformat(candle["source_date"]), holding_sessions=i,
                        tp1_taken=seen_tp1, policy=TradePolicy(**position["policy"]))
                    observations.append(review)
                    if review["status"] != "reviewed":
                        break
                result["observations"] = observations
                if len(observations) == len(rows) and all(r["status"] == "reviewed" for r in observations):
                    last_fill = position["fills"][-1]["date"] if position["fills"] else position["entry_date"]
                    alerts = [r for r in observations if r["action"] != "HOLD" and r["as_of"] > last_fill]
                    # Report prior exit triggers even if the newest price recovered.
                    exit_alerts = [r for r in alerts if r["action"] in {"EXIT_REVIEW", "TIME_EXIT_REVIEW"}]
                    chosen = exit_alerts[0] if exit_alerts else alerts[-1] if alerts else None
                    result.update(status="reviewed", action=chosen["action"] if chosen else "HOLD",
                                  latest_action=observations[-1]["action"], alerts=alerts,
                                  reason="Historical triggers require reconciliation with reported fills")
            key = hashlib.sha256(_encoded({"position": position, "history": history, "as_of": as_of.isoformat()}).encode()).hexdigest()
            result["review_id"] = key
            con.execute("INSERT OR IGNORE INTO position_reviews VALUES(?,?,?)", (key, position_id, _encoded(result)))
            return result

    def raise_stop(self, position_id: str, *, request_id: str, stop: float,
                   effective_on: date) -> dict[str, Any]:
        """A reported stop change applies only to future sessions, never history."""
        self._request_id(request_id)
        _finite_positive(stop, "stop")
        payload = _encoded(dict(kind="RAISE_STOP", position_id=position_id,
                                stop=stop, effective_on=effective_on.isoformat()))
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = self._existing(con, request_id, payload)
            if prior is not None:
                return prior
            row = con.execute("SELECT payload FROM positions WHERE id=?", (position_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("Position not found")
            position = json.loads(row[0])
            previous = position["stop_changes"][-1] if position["stop_changes"] else None
            baseline = previous["stop"] if previous else position["stop"]
            next_target = position["tp2"] if any(f["reason"] == "TP1" for f in position["fills"]) else position["tp1"]
            if (position["status"] == "CLOSED" or effective_on <= _today() or
                    (previous and effective_on.isoformat() <= previous["effective_on"]) or
                    not baseline < stop < next_target):
                raise ValueError("Stop must increase below the next target and apply on a future day")
            position["stop_changes"].append({"stop": stop, "effective_on": effective_on.isoformat()})
            self._save_event(con, request_id, payload, position)
            return position
