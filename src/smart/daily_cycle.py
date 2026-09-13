"""Checkpointed daily watchlist scans shared by the dashboard and CLI.

Reports retain the exact scanner responses. Ranking uses the historical factor
score and close, never substitutes retrieval time for the date of market data.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .persian_text import normalize_persian_text

REPORT_TIMEZONE = timezone(timedelta(hours=3, minutes=30))
LEASE_SECONDS = 600
ACTIVE_STATUSES = {"queued", "running"}
Scanner = Callable[[list[str]], Awaitable[dict[str, Any]]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_symbols(symbols: list[str]) -> list[str]:
    if not isinstance(symbols, list) or not all(isinstance(s, str) for s in symbols):
        raise ValueError("symbols must be a list of names")
    cleaned = list(dict.fromkeys(normalize_persian_text(s) for s in symbols if s.strip()))
    if not cleaned or len(cleaned) > 20 or any(len(s) > 80 for s in cleaned):
        raise ValueError("provide 1 to 20 distinct symbols, at most 80 characters each")
    return cleaned


def default_store_path() -> Path:
    return Path(os.getenv("SMART_DAILY_DB", "runtime/daily_reports.sqlite3"))


class ActiveRunError(RuntimeError):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__("a daily scan is already in progress")


class DailyRunStore:
    """SQLite transactions guard checkpoints and one active run across processes."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS daily_runs (
                run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                status TEXT NOT NULL, lease_until TEXT, payload TEXT NOT NULL
            )""")
            con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_active_daily_run
                ON daily_runs ((1)) WHERE status IN ('queued', 'running')""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def _write(con, report: dict, now: datetime):
        active = report["status"] in ACTIVE_STATUSES
        lease = (now + timedelta(seconds=LEASE_SECONDS)).isoformat() if active else None
        report["updated_at"] = now.isoformat()
        con.execute(
            "UPDATE daily_runs SET status=?, lease_until=?, payload=? WHERE run_id=?",
            (report["status"], lease, json.dumps(report, ensure_ascii=False, allow_nan=False),
             report["run_id"]),
        )

    @classmethod
    def _expire(cls, con, now: datetime):
        for (raw,) in con.execute(
            "SELECT payload FROM daily_runs WHERE status IN ('queued','running') "
            "AND lease_until < ?", (now.isoformat(),),
        ).fetchall():
            report = json.loads(raw)
            report.update(status="interrupted", finished_at=now.isoformat())
            report["errors"].append({"symbol": None, "code": "worker_interrupted",
                                     "error": "worker stopped before completing the report"})
            cls._write(con, report, now)

    def create(self, symbols: list[str], *, max_age_days: int = 3,
               now: datetime | None = None) -> dict:
        symbols = normalize_symbols(symbols)
        if type(max_age_days) is not int or not 0 <= max_age_days <= 30:
            raise ValueError("max_age_days must be an integer from 0 to 30")
        now = (now or utc_now()).astimezone(timezone.utc)
        report = {
            "schema_version": "daily-cycle-v1", "run_id": uuid.uuid4().hex,
            "status": "queued", "created_at": now.isoformat(), "updated_at": now.isoformat(),
            "started_at": None, "finished_at": None,
            "report_date": now.astimezone(REPORT_TIMEZONE).date().isoformat(),
            "report_timezone": "+03:30", "symbols_requested": symbols,
            "max_age_days": max_age_days, "processed_count": 0, "current_symbol": None,
            "results": [], "errors": [], "top_10": [],
            "ranking_scope": "requested_watchlist_only",
            "ranking_basis": "historical_factor_score_descending",
            "counts": {"requested": len(symbols), "received": 0, "eligible": 0, "excluded": 0},
        }
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            active = con.execute(
                "SELECT run_id FROM daily_runs WHERE status IN ('queued','running')"
            ).fetchone()
            if active:
                raise ActiveRunError(active[0])
            con.execute("INSERT INTO daily_runs VALUES (?, ?, ?, ?, ?)", (
                report["run_id"], report["created_at"], report["status"],
                (now + timedelta(seconds=LEASE_SECONDS)).isoformat(),
                json.dumps(report, ensure_ascii=False, allow_nan=False),
            ))
        return report

    def get(self, run_id: str, *, now: datetime | None = None) -> dict:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now or utc_now())
            row = con.execute("SELECT payload FROM daily_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("daily report not found")
        return json.loads(row[0])

    def list(self, *, limit: int = 20) -> list[dict]:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, utc_now())
            rows = con.execute("SELECT payload FROM daily_runs ORDER BY created_at DESC, "
                               "run_id DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [self.summary(json.loads(row[0])) for row in rows]

    @staticmethod
    def summary(report: dict) -> dict:
        return {key: value for key, value in report.items() if key not in {"results", "top_10"}}

    def claim(self, run_id: str) -> dict | None:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            now = utc_now()
            self._expire(con, now)
            row = con.execute("SELECT payload FROM daily_runs WHERE run_id=? AND status='queued'",
                              (run_id,)).fetchone()
            if row is None:
                return None
            report = json.loads(row[0])
            report.update(status="running", started_at=now.isoformat())
            self._write(con, report, now)
        return report

    def checkpoint(self, report: dict) -> bool:
        """A timed-out or finished worker can never overwrite a stored report."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            now = utc_now()
            self._expire(con, now)
            row = con.execute("SELECT status FROM daily_runs WHERE run_id=?",
                              (report["run_id"],)).fetchone()
            if row is None or row[0] != "running":
                return False
            self._write(con, report, now)
        return True


def _date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def assess_result(row: dict, *, report_date: str, max_age_days: int) -> dict:
    """Fail closed for absent dates, poor quality, stale/future or unpriced bars."""
    contract = row.get("structured_analysis") or {}
    analysis = row.get("analysis") or {}
    latest = (analysis.get("technical_history") or row.get("technical_history") or {}).get(
        "latest", {})
    as_of = _date(contract.get("as_of"))
    bar_date = _date(latest.get("date"))
    age = (date.fromisoformat(report_date) - as_of).days if as_of else None
    freshness = ("unknown" if age is None else "future" if age < 0 else
                 "stale" if age > max_age_days else "same_day" if age == 0 else "recent_history")
    quality = (contract.get("data_quality") or {}).get("status", "unknown")
    final = contract.get("final_assessment") or {}
    score = _number(final.get("score_0_100"))
    close = _number(latest.get("close"))
    reasons = []
    if freshness not in {"same_day", "recent_history"}:
        reasons.append("data_" + freshness)
    if bar_date is None or bar_date != as_of:
        reasons.append("bar_date_mismatch")
    if quality != "good":
        reasons.append("quality_" + quality)
    if close is None or close <= 0:
        reasons.append("missing_close")
    if score is None or not 0 <= score <= 100:
        reasons.append("invalid_score")
    return {
        "symbol": row["symbol"], "as_of": as_of.isoformat() if as_of else None,
        "close": close, "score": score, "quality": quality,
        "freshness": freshness, "age_days": age,
        "eligible": not reasons, "exclusion_reasons": reasons,
        "decision_id": (row.get("decision_record") or {}).get("decision_id"),
    }


def _refresh_counts(report: dict):
    candidates = sorted(
        (row["assessment"] for row in report["results"] if row["assessment"]["eligible"]),
        key=lambda row: (-row["score"], row["symbol"]),
    )
    report["top_10"] = [dict(row, rank=i) for i, row in enumerate(candidates[:10], start=1)]
    report["counts"].update(received=len(report["results"]), eligible=len(candidates),
                            excluded=report["processed_count"] - len(candidates))


async def execute_daily_run(store: DailyRunStore, run_id: str, scanner: Scanner,
                            *, symbol_timeout: float = 120) -> dict:
    report = store.claim(run_id)
    if report is None:
        return store.get(run_id)
    try:
        for symbol in report["symbols_requested"]:
            report["current_symbol"] = symbol
            if not store.checkpoint(report):
                return store.get(run_id)
            try:
                snapshot = await asyncio.wait_for(scanner([symbol]), timeout=symbol_timeout)
                # Validate serializability before retaining any provider response.
                json.dumps(snapshot, allow_nan=False)
                rows = snapshot.get("results") or []
                row = next((r for r in rows if isinstance(r, dict) and
                            normalize_persian_text(r.get("symbol")) == symbol), None)
                errors = snapshot.get("errors") or []
                report["errors"].extend({"symbol": symbol, "code": "source_error",
                                         "error": str(error.get("error", "source unavailable"))}
                                        for error in errors if isinstance(error, dict))
                if row is None:
                    if not errors:
                        report["errors"].append({"symbol": symbol, "code": "missing_result",
                                                 "error": "scanner returned no matching symbol"})
                else:
                    assessment = assess_result(row, report_date=report["report_date"],
                                               max_age_days=report["max_age_days"])
                    if errors:
                        assessment["eligible"] = False
                        assessment["exclusion_reasons"].append("source_errors")
                    report["results"].append({"assessment": assessment, "snapshot": snapshot})
            except TimeoutError:
                report["errors"].append({"symbol": symbol, "code": "timeout",
                                         "error": "symbol scan exceeded its time limit"})
            except Exception as exc:
                report["errors"].append({"symbol": symbol, "code": "scan_error",
                                         "error": f"{type(exc).__name__}: {exc}"})
            report["processed_count"] += 1
            report["current_symbol"] = None
            _refresh_counts(report)
            if not store.checkpoint(report):
                return store.get(run_id)
        report["status"] = ("failed" if not report["results"] else "partial" if
                            report["errors"] or report["counts"]["excluded"] else "completed")
        report["finished_at"] = utc_now().isoformat()
        store.checkpoint(report)
        return store.get(run_id)
    except (asyncio.CancelledError, KeyboardInterrupt):
        report.update(status="interrupted", finished_at=utc_now().isoformat(), current_symbol=None)
        report["errors"].append({"symbol": None, "code": "worker_interrupted",
                                 "error": "daily cycle was interrupted"})
        store.checkpoint(report)
        raise
