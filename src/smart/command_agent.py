"""Safe GitHub command bridge for the local SMART Iran agent."""
from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

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
    return {"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def get_file(path: str) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{API}/repos/{REPO}/contents/{path}?ref={BRANCH}"
    r = requests.get(url, headers=headers(), timeout=20)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    body = r.json()
    content = base64.b64decode(body["content"]).decode("utf-8")
    return json.loads(content), body["sha"]


def put_json(path: str, payload: dict[str, Any], message: str, sha: str | None = None) -> None:
    url = f"{API}/repos/{REPO}/contents/{path}"
    if sha is None:
        # GitHub requires the current blob SHA when replacing an existing file.
        try:
            _, sha = get_file(path)
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(json.dumps(payload, ensure_ascii=False, indent=2).encode()).decode(),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=headers(), json=body, timeout=20)
    r.raise_for_status()


def execute(command: dict[str, Any]) -> dict[str, Any]:
    action = command.get("action")
    if action != "fetch_tsetmc":
        raise ValueError("Unsupported action. Allowed action: fetch_tsetmc")
    symbol = str(command.get("symbol", "")).strip()
    if not symbol or len(symbol) > 32:
        raise ValueError("A valid symbol is required")
    result = TsetmcAdapter().collect_symbol(symbol)
    return {"request_id": command.get("request_id"), "status": "success", "completed_at": datetime.now(timezone.utc).isoformat(), "action": action, "symbol": symbol, "data": result}


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
        result = {"request_id": request_id, "status": "error", "completed_at": datetime.now(timezone.utc).isoformat(), "error": type(exc).__name__ + ": " + str(exc)}
    result["command_sha"] = command_sha
    put_json(RESULT_PATH, result, f"agent: result for {request_id}")
    if result.get("status") == "success":
        put_json(f"runtime/snapshots/{result['symbol']}/{request_id}.json", _compact_snapshot(result), f"agent: snapshot {result['symbol']} {request_id}")
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
