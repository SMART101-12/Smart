"""Safe GitHub command bridge for the local SMART Iran agent."""
from __future__ import annotations

import base64
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .tsetmc_adapter import TsetmcAdapter

REPO = os.getenv("SMART_GITHUB_REPO", "SMART101-12/Smart")
BRANCH = os.getenv("SMART_GITHUB_BRANCH", "main")
COMMAND_PATH = os.getenv("SMART_COMMAND_PATH", "runtime/command.json")
RESULT_PATH = os.getenv("SMART_RESULT_PATH", "runtime/result.json")
POLL_SECONDS = int(os.getenv("SMART_POLL_SECONDS", "10"))
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[2]
LAST_REQUEST_FILE = ROOT / "runtime" / "last_request_id.txt"


def token() -> str:
    value = os.getenv("SMART_GITHUB_TOKEN")
    if value:
        return value
    try:
        import keyring
        value = keyring.get_password("SMART-GitHub", "github-token")
    except Exception:
        value = None
    if not value:
        raise RuntimeError("GitHub token is not configured. Run the SMART installer/setup once.")
    return value


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _session() -> requests.Session:
    """HTTP session with bounded retries for transient GitHub/network failures."""
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "PUT"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Retry transient SSL/connection failures with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            response = _session().request(method, url, **kwargs)
            return response
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt == 5:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))
    raise last_exc  # type: ignore[misc]


def get_file(path: str) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{API}/repos/{REPO}/contents/{path}?ref={BRANCH}"
    r = _request("GET", url, headers=headers(), timeout=(15, 45))
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    body = r.json()
    content = base64.b64decode(body["content"]).decode("utf-8")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    return parsed, body["sha"]


def put_json(path: str, payload: dict[str, Any], message: str, sha: str | None = None) -> None:
    url = f"{API}/repos/{REPO}/contents/{path}"
    if sha is None:
        _, sha = get_file(path)
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(json.dumps(payload, ensure_ascii=False, indent=2).encode()).decode(),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    r = _request("PUT", url, headers=headers(), json=body, timeout=(15, 90))
    r.raise_for_status()


def execute(command: dict[str, Any]) -> dict[str, Any]:
    action = command.get("action")
    if action != "fetch_tsetmc":
        raise ValueError("Unsupported action. Allowed action: fetch_tsetmc")
    symbol = str(command.get("symbol", "")).strip()
    if not symbol or len(symbol) > 32:
        raise ValueError("A valid symbol is required")
    result = TsetmcAdapter().collect_symbol(symbol)
    return {
        "request_id": command.get("request_id"),
        "status": "success",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "symbol": symbol,
        "data": result,
    }


def _compact_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data", {})
    payload = data.get("payload", {})
    history = payload.get("daily_history", [])
    return {
        "request_id": result.get("request_id"),
        "symbol": result.get("symbol"),
        "source": data.get("source"),
        "observed_at": data.get("observed_at"),
        "ins_code": data.get("ins_code"),
        "history_rows": len(history),
        "latest_history": history[0] if history else None,
        "oldest_history": history[-1] if history else None,
        "closing_price": payload.get("closing_price"),
        "client_type": payload.get("client_type"),
        "instrument": payload.get("instrument"),
    }


def _history_export(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data", {})
    payload = data.get("payload", {})
    history = payload.get("daily_history", [])
    return {
        "symbol": result.get("symbol"),
        "ins_code": data.get("ins_code"),
        "source": data.get("source"),
        "exported_at": result.get("completed_at"),
        "history_rows": len(history),
        "first_history_date": history[-1].get("dEven") if history else None,
        "last_history_date": history[0].get("dEven") if history else None,
        "fields_note": "Raw TSETMC daily history. dEven=market date, pClosing=closing price, pDrCotVal=last/traded price, qTotTran5J=volume, qTotCap=trade value, zTotTran=trade count.",
        "daily_history": history,
    }


def _monthly_history_exports(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Keep raw monthly history for audit/reprocessing."""
    data = result.get("data", {})
    payload = data.get("payload", {})
    history = payload.get("daily_history", [])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history:
        raw = str(row.get("dEven", "")).strip()
        if len(raw) == 8 and raw.isdigit():
            groups[raw[:6]].append(row)
    return {
        month: {
            "symbol": result.get("symbol"),
            "ins_code": data.get("ins_code"),
            "source": data.get("source"),
            "month": month,
            "exported_at": result.get("completed_at"),
            "rows": len(rows),
            "fields_note": "dEven=YYYYMMDD, pClosing=closing price, pDrCotVal=last/traded price, qTotTran5J=volume, qTotCap=trade value, zTotTran=trade count.",
            "daily_history": sorted(rows, key=lambda r: int(r.get("dEven", 0)), reverse=True),
        }
        for month, rows in groups.items()
    }


def _monthly_lookup_exports(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Create tiny, date-addressable monthly files for reliable Git reads."""
    data = result.get("data", {})
    payload = data.get("payload", {})
    history = payload.get("daily_history", [])
    fields = (
        "dEven", "pClosing", "pDrCotVal", "priceFirst", "priceMin", "priceMax",
        "priceYesterday", "priceChange", "zTotTran", "qTotTran5J", "qTotCap",
        "iClose", "yClose", "last", "hEven"
    )
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history:
        raw = str(row.get("dEven", "")).strip()
        if len(raw) != 8 or not raw.isdigit():
            continue
        groups[raw[:6]].append({k: row.get(k) for k in fields if k in row})
    return {
        month: {
            "symbol": result.get("symbol"),
            "ins_code": data.get("ins_code"),
            "source": data.get("source"),
            "month": month,
            "updated_at": result.get("completed_at"),
            "rows": len(rows),
            "schema": {
                "dEven": "YYYYMMDD",
                "pClosing": "closing price (rial)",
                "pDrCotVal": "last/traded price (rial)",
                "qTotTran5J": "volume (shares)",
                "qTotCap": "trade value (rial)",
                "zTotTran": "trade count",
            },
            "daily": sorted(rows, key=lambda r: int(r.get("dEven", 0)), reverse=True),
        }
        for month, rows in groups.items()
    }


def _load_last() -> str | None:
    try:
        return LAST_REQUEST_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _save_last(request_id: str) -> None:
    LAST_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_REQUEST_FILE.write_text(request_id, encoding="utf-8")


def run_once(last_request_id: str | None = None) -> str | None:
    command, command_sha = get_file(COMMAND_PATH)
    if not command or not command.get("request_id") or command.get("request_id") == last_request_id:
        return last_request_id
    request_id = str(command["request_id"])
    try:
        result = execute(command)
    except Exception as exc:
        result = {
            "request_id": request_id,
            "status": "error",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": type(exc).__name__ + ": " + str(exc),
        }
    result["command_sha"] = command_sha
    put_json(RESULT_PATH, result, f"agent: result for {request_id}")
    if result.get("status") == "success":
        symbol = result["symbol"]
        put_json(f"runtime/snapshots/{symbol}/{request_id}.json", _compact_snapshot(result), f"agent: snapshot {symbol} {request_id}")
        put_json(f"runtime/history/{symbol}.json", _history_export(result), f"agent: full history {symbol} {request_id}")

        # The compact monthly lookup layer is canonical for historical queries.
        # Raw monthly files are intentionally NOT rewritten on every run: they
        # create unnecessary GitHub API traffic and were the source of the
        # previous long-run SSL failure. The full history file remains the
        # audit/reprocessing source.
        for month, month_payload in _monthly_lookup_exports(result).items():
            put_json(
                f"runtime/history_lookup/{symbol}/{month}.json",
                month_payload,
                f"agent: date lookup {symbol} {month} {request_id}",
            )
    _save_last(request_id)
    return request_id


def main() -> None:
    last = _load_last()
    print(f"SMART command agent listening: {REPO}/{COMMAND_PATH}", flush=True)
    while True:
        try:
            last = run_once(last)
        except Exception as exc:
            print(f"agent loop error: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
