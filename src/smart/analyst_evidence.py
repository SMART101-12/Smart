"""Job-scoped public source evidence, including rejected HTTP responses."""
from __future__ import annotations

import base64
import contextvars
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

_capture = contextvars.ContextVar("source_evidence", default=None)


class SourceCapture:
    def __init__(self, directory: Path):
        self.path = directory / "source_responses.jsonl"
        self.records = []
        self.lock = RLock()
        self.closed = False

    def freeze(self):
        with self.lock:
            self.closed = True
            return {"responses": list(self.records)}

    def record(self, url: str, body: bytes, *, status: int | None = None,
               content_type: str = "", origin: str = "http"):
        # Never store request headers, cookies, API credentials or model traffic.
        with self.lock:
            if self.closed:
                return
            record = {"url": url, "status": status, "origin": origin,
                "content_type": content_type, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "body_base64": base64.b64encode(body).decode("ascii")}
            # Append each received body once. Rewriting the whole capture on
            # every request would become quadratic during a long source sync.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as journal:
                journal.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            self.records.append(record)


def capture_response(url: str, body: bytes, **metadata):
    collector = _capture.get()
    if collector is not None:
        collector.record(url, body, **metadata)


def capture_cached(url: str, payload: dict):
    capture_response(url, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                     origin="cached_json", content_type="application/json")


def repository_evidence(repository, symbol: str, ins_code: str) -> dict:
    """Copy persisted provider evidence, with explicit scope and no silent caps."""
    from .financial_history import normalize
    symbol = normalize(symbol)
    tables = ("financial_documents", "codal_announcements", "codal_monthly_reports", "codal_assets",
              "financial_parse_history", "historical_sync_log", "historical_sync_state")
    result = {}
    with repository._connect() as connection:
        for table in tables:
            cursor = connection.execute(f"SELECT * FROM {table} WHERE symbol=?", (symbol,))
            names = [column[0] for column in cursor.description]
            rows = []
            for values in cursor:
                row = dict(zip(names, values))
                for key, value in list(row.items()):
                    if isinstance(value, bytes):
                        row[key] = {"encoding": "base64", "sha256": hashlib.sha256(value).hexdigest(),
                                    "value": base64.b64encode(value).decode("ascii")}
                rows.append(row)
            result[table] = rows
        cursor = connection.execute("SELECT source,observed_at,market_date,payload FROM market_snapshots WHERE symbol IN (?,?)",
                                    (symbol, str(ins_code)))
        result["market_snapshots"] = [dict(zip(("source", "observed_at", "market_date", "payload"), row)) for row in cursor]
        cursor = connection.execute("SELECT request_date,payload FROM historical_sync_log WHERE symbol=? AND source='TSETMC' ORDER BY id",
                                    (str(ins_code),))
        result["market_sync_log"] = [{"request_date": stamp, "payload": json.loads(payload)} for stamp, payload in cursor]
    result["market_history"] = repository.history(ins_code, "tsetmc")
    result["market_history_alias"] = repository.history(symbol, "tsetmc")
    result["market_sync"] = repository.state(ins_code, "TSETMC")
    result["scope"] = "All currently persisted evidence for this symbol; retrieval may postdate analysis as_of. Use quality gates and publication dates before analysis."
    return result
