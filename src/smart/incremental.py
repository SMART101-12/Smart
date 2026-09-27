"""Incremental TSETMC history synchronization.

The synchronizer deliberately separates three concerns:

* discover dates already present in SQLite and monthly JSON archives;
* ask TSETMC only for dates that are expected and missing;
* merge/deduplicate rows and write a deterministic monthly archive.

It never deletes raw evidence and it never treats an unresolved date as a
zero-valued market record.  Unresolved dates are persisted in a quality report
so a later run can retry them.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .archive import archive_monthly, safe_symbol
from .snapshot_store import SnapshotStore


def parse_market_date(value: Any) -> date | None:
    raw = str(value or "").replace("-", "").replace("/", "").strip()
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def format_tsetmc_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def expected_market_dates(
    start: date,
    end: date,
    *,
    closed_dates: set[date] | None = None,
    closed_weekdays: set[int] = frozenset({3, 4}),
) -> list[date]:
    """Return candidate Iranian trading dates in chronological order."""
    if end < start:
        return []
    closed = closed_dates or set()
    result: list[date] = []
    current = start
    while current <= end:
        if current.weekday() not in closed_weekdays and current not in closed:
            result.append(current)
        current += timedelta(days=1)
    return result


class IncrementalHistorySync:
    """Synchronize one TSETMC instrument without refetching full history."""

    def __init__(
        self,
        adapter: Any,
        *,
        store: SnapshotStore | None = None,
        history_root: str | Path = "runtime/history",
        quality_root: str | Path = "runtime/data_quality",
        canonical_root: str | Path = "runtime/market_processed/canonical",
    ) -> None:
        self.adapter = adapter
        self.store = store or getattr(adapter, "store", None) or SnapshotStore()
        self.history_root = Path(history_root)
        self.quality_root = Path(quality_root)
        self.canonical_root = Path(canonical_root)

    def _load_archived_rows(self, symbol: str) -> tuple[dict[date, dict[str, Any]], dict[str, Any]]:
        rows: dict[date, dict[str, Any]] = {}
        metadata: dict[str, Any] = {"symbol": symbol, "source": "tsetmc"}
        directory = self.history_root / safe_symbol(symbol)
        paths = list(directory.glob("*.json")) if directory.exists() else []
        # Keep compatibility with the original flat SMART layout
        # ``runtime/history/<symbol>.json``.
        flat = self.history_root / f"{safe_symbol(symbol)}.json"
        if flat.exists():
            paths.append(flat)
        for path in sorted(paths):
            if path.stem == "metadata" or not path.stem.isdigit():
                # A flat file is allowed even though its stem is the symbol.
                if path != flat:
                    continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            for key in ("symbol", "ins_code", "source"):
                if payload.get(key):
                    metadata[key] = payload[key]
            source_rows = payload.get("daily_history") or payload.get("records") or []
            for row in source_rows:
                if not isinstance(row, dict):
                    continue
                parsed = parse_market_date(row.get("dEven") or row.get("date"))
                if parsed:
                    rows[parsed] = row
        return rows, metadata

    @staticmethod
    def _row_date(row: dict[str, Any]) -> date | None:
        return parse_market_date(row.get("dEven") or row.get("date") or row.get("market_date"))

    def _db_rows(self, symbol: str, source: str = "tsetmc") -> dict[date, dict[str, Any]]:
        try:
            records = self.store.history(symbol, source)
        except Exception:
            return {}
        result: dict[date, dict[str, Any]] = {}
        for item in records:
            row = item.get("payload")
            if isinstance(row, dict):
                parsed = self._row_date(row) or parse_market_date(item.get("market_date"))
                if parsed:
                    result[parsed] = row
        return result

    def _closed_dates(self, ins_code: str, start: date, end: date) -> set[date]:
        try:
            calendar = self.adapter.instrument_calendar(ins_code)
        except Exception:
            return set()
        result: set[date] = set()
        for item in calendar:
            if not isinstance(item, dict):
                continue
            parsed = parse_market_date(
                item.get("dEven") or item.get("date") or item.get("market_date")
            )
            # Calendar endpoints generally return open/traded dates, not
            # closures.  Only explicit closed flags are interpreted here.
            is_closed = item.get("closed") is True or str(item.get("status", "")).upper() in {
                "CLOSED",
                "HOLIDAY",
            }
            if parsed and is_closed and start <= parsed <= end:
                result.add(parsed)
        return result

    def _write_archives(
        self,
        symbol: str,
        ins_code: str,
        rows: dict[date, dict[str, Any]],
        *,
        observed_at: datetime,
    ) -> list[str]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for parsed, row in sorted(rows.items()):
            grouped[parsed.strftime("%Y%m")].append(row)
        written: list[str] = []
        for month, month_rows in grouped.items():
            target = self.history_root / safe_symbol(symbol) / f"{month}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": "2.1",
                "source": "tsetmc",
                "symbol": symbol,
                "ins_code": ins_code,
                "month": month,
                "exported_at": observed_at.isoformat(),
                "rows": len(month_rows),
                "daily_history": month_rows,
            }
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
                encoding="utf-8",
            )
            written.append(str(target))
        return written

    def _write_quality(self, symbol: str, report: dict[str, Any]) -> str:
        self.quality_root.mkdir(parents=True, exist_ok=True)
        target = self.quality_root / f"{safe_symbol(symbol)}.json"
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(target)

    def sync(
        self,
        symbol: str,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        closed_dates: set[date] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        instrument = self.adapter.resolve_symbol(symbol)
        ins_code = str(instrument.get("insCode") or instrument.get("ins_code") or "")
        if not ins_code:
            raise RuntimeError(f"TSETMC did not return an InsCode for {symbol}")

        archived, metadata = self._load_archived_rows(symbol)
        database = self._db_rows(symbol)
        rows = {**database, **archived}  # file archive is the reproducible source
        initial_full_fetch = False
        initial_rows: list[dict[str, Any]] = []
        parsed_start = parse_market_date(start_date) if start_date is not None else None
        parsed_end = parse_market_date(end_date) if end_date is not None else None
        if parsed_start is None:
            parsed_start = min(rows) if rows else None
        if parsed_end is None:
            parsed_end = datetime.now(timezone.utc).date() - timedelta(days=1)
        if not rows:
            # A first acquisition still uses the full endpoint once, even
            # when the caller supplied an explicit date range.  All
            # subsequent runs use the date-specific endpoint below.
            history = self.adapter.daily_history(ins_code, 0)
            initial_full_fetch = True
            for row in history:
                parsed = self._row_date(row) if isinstance(row, dict) else None
                if parsed:
                    rows[parsed] = row
                    initial_rows.append(row)
            parsed_start = min(rows) if rows else parsed_end

        excluded = set(closed_dates or set()) | self._closed_dates(ins_code, parsed_start, parsed_end)
        expected = expected_market_dates(parsed_start, parsed_end, closed_dates=excluded)
        # The full endpoint is authoritative for a first acquisition.  Do not
        # turn every historical holiday/weekend into a separate HTTP request
        # immediately after downloading the complete series.
        missing = [] if initial_full_fetch else [d for d in expected if d not in rows]
        fetched: list[dict[str, Any]] = list(initial_rows)
        unresolved: list[str] = []
        if not dry_run and missing:
            incremental_rows, unresolved = self.adapter.daily_history_incremental(
                ins_code, [format_tsetmc_date(d) for d in missing]
            )
            fetched.extend(incremental_rows)
            for row in incremental_rows:
                parsed = self._row_date(row)
                if parsed:
                    rows[parsed] = row

        observed_at = datetime.now(timezone.utc)
        persistence = {"inserted": 0, "updated": 0, "skipped": 0}
        if not dry_run and fetched:
            persistence = self.store.save_daily_history_incremental(
                symbol, "tsetmc", observed_at, fetched
            )
        archive_paths: list[str] = []
        canonical_report: dict[str, Any] | None = None
        if not dry_run:
            archive_paths = self._write_archives(symbol, ins_code, rows, observed_at=observed_at)
            canonical_report = archive_monthly(
                symbol,
                rows.values(),
                root=self.canonical_root,
                ins_code=ins_code,
                source="TSETMC",
                metadata={
                    "sync_source": "IncrementalHistorySync",
                    "instrument": instrument,
                },
            )

        report = {
            "schema_version": "1.0",
            "symbol": symbol,
            "ins_code": ins_code,
            "source": "TSETMC",
            "status": "COMPLETE"
            if (initial_full_fetch and not unresolved)
            or (not unresolved and not [d for d in expected if d not in rows])
            else "PARTIAL",
            "dry_run": dry_run,
            "range": {
                "start": parsed_start.isoformat() if parsed_start else None,
                "end": parsed_end.isoformat() if parsed_end else None,
            },
            "existing_rows": len(archived),
            "database_rows": len(database),
            "expected_dates": len(expected),
            "missing_before_fetch": len(missing),
            "fetched_rows": len(fetched),
            "unresolved_dates": unresolved,
            "remaining_missing_dates": [
                d.isoformat() for d in expected if d not in rows
            ],
            "persistence": persistence,
            "archive_paths": archive_paths,
            "canonical_archive": canonical_report,
            "updated_at": observed_at.isoformat(),
            "instrument": instrument,
        }
        if not dry_run:
            report["quality_report"] = self._write_quality(symbol, report)
        return report


__all__ = [
    "IncrementalHistorySync",
    "expected_market_dates",
    "format_tsetmc_date",
    "parse_market_date",
]
