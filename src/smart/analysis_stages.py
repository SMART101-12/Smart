"""Stage deadlines, evidence status and durable progress for analysis jobs."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .atomic_json import write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_status(value: Any) -> str:
    """Execution success does not imply that the returned evidence is complete."""
    if value is None:
        return "NOT_AVAILABLE"
    if not isinstance(value, dict) or "status" not in value:
        return "COMPLETED"
    status = str(value["status"]).strip().upper()
    if status in {"SUCCESS", "COMPLETE", "COMPLETED", "VERIFIED", "PASS", "OK", "READY", "AVAILABLE", "ANALYZED", "NO_SETUP"}:
        return "COMPLETED"
    return "PARTIAL"


class StageRunner:
    def __init__(self, job: dict, directory: Path, timeout: float) -> None:
        self.job = job
        self.directory = directory
        self.timeout = timeout

    async def __call__(self, name: str, action: Callable[[], Awaitable[Any]]) -> Any:
        job, directory = self.job, self.directory
        symbol = job["symbol"]
        start = time.monotonic()
        job["stage"] = name
        write_json(directory / "job.json", job)
        try:
            value = await asyncio.wait_for(action(), timeout=self.timeout)
            state = _stage_status(value)
            if state != "COMPLETED":
                detail = "No stage result"
                if isinstance(value, dict):
                    detail = value.get("reason") or value.get("error") or value.get("status")
                job["warnings"].append({"stage": name, "error": str(detail)})
        except Exception as exc:
            value = None
            state = "NOT_AVAILABLE"
            job["warnings"].append({"stage": name, "error":
                                   "Stage execution budget exceeded" if isinstance(exc, TimeoutError) else str(exc)})
        job["stages"].append({"name": name, "status": state,
                              "seconds": round(time.monotonic() - start, 3)})
        with (directory / "analysis.log").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"timestamp": _now(), "symbol": symbol, "stage": name,
                                  "duration": job["stages"][-1]["seconds"],
                                  "source": "TSETMC" if name in {"symbol", "market_and_technical", "historical_data"}
                                            else "KODAL" if name in {"codal_sync", "fundamental"}
                                            else "local", "status": state,
                                  "error": job["warnings"][-1]["error"] if state != "COMPLETED" else None},
                                 ensure_ascii=False) + "\n")
        write_json(directory / "job.json", job)
        return value
