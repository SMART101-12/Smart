"""Safe GitHub command bridge for the local SMART Iran agent.

The local process polls a single command JSON file in the public/private
repository. Only allow-listed market-data actions are executable; arbitrary
shell commands are never accepted. Results are written back through the
GitHub Contents API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .tsetmc_adapter import TsetmcAdapter

REPO = os.getenv("SMART_GITHUB_REPO", "SMART101-12/Smart")
BRANCH = os.getenv("SMART_GITHUB_BRANCH", "main")
COMMAND_PATH = os.getenv("SMART_COMMAND_PATH", "runtime/command.json")
RESULT_PATH = os.getenv("SMART_RESULT_PATH", "runtime/result.json")
POLL_SECONDS = int(os.getenv("SMART_POLL_SECONDS", "10"))
API = "https://api.github.com"


def token() -> str:
    value = os.getenv("SMART_GITHUB_TOKEN")
    if not value:
        raise RuntimeError("SMART_GITHUB_TOKEN is not set")
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


def put_file(path: str, payload: dict[str, Any], message: str, sha: str | None = None) -> None:
    url = f"{API}/repos/{REPO}/contents/{path}"
    body: dict[str, Any] = {"message": message, "content": base64.b64encode(json.dumps(payload, ensure_ascii=False, indent=2).encode()).decode(), "branch": BRANCH}
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
    return {
        "request_id": command.get("request_id"),
        "status": "success",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "symbol": symbol,
        "data": result,
    }


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
    put_file(RESULT_PATH, result, f"agent: result for {request_id}")
    return request_id


def main() -> None:
    last = None
    print(f"SMART command agent listening: {REPO}/{COMMAND_PATH}")
    while True:
        try:
            last = run_once(last)
        except Exception as exc:
            print(f"agent loop error: {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
