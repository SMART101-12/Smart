"""Reuse deterministic research only when every recorded input matches."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
import contextlib
from functools import lru_cache
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import Awaitable, Callable, Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def implementation_fingerprint() -> str:
    root = Path(__file__).parent
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob("*.py"))}
    dependencies = {}
    for name in ("numpy", "pandas", "scikit-learn", "scipy"):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = "not-installed"
    return digest({"source_files": files, "dependencies": dependencies})


async def cached_research(kind: str, inputs: dict,
                          compute: Callable[[], Awaitable[Any]]) -> tuple[Any, dict]:
    if kind not in {"historical_exam", "long_only_oos"}:
        raise ValueError("Unknown research cache kind")
    key = digest({"schema": "RESEARCH-CACHE-1", "kind": kind,
                  "implementation": implementation_fingerprint(), "inputs": inputs})
    root = Path(os.getenv("SMART_RESEARCH_CACHE", "runtime/research_cache"))
    path = root / kind / (key + ".json")
    state = "MISS"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["key"] == key and cached["result_sha256"] == digest(cached["result"]):
            return cached["result"], {"key": key, "state": "HIT", "reused": True}
        state = "INVALIDATED"
    except FileNotFoundError:
        pass
    except (ValueError, KeyError, TypeError, OSError):
        state = "INVALIDATED"
    value = await compute()
    # Incomplete/failed computation is not cached as valid research.
    if not isinstance(value, dict) or value.get("status") in {
            "FAILED", "PARTIAL", "UNAVAILABLE", "SOURCE_UNAVAILABLE", "INSUFFICIENT_DATA",
            "INSUFFICIENT_HISTORY", "NOT_AVAILABLE"}:
        return value, {"key": key, "state": "NOT_CACHED", "reused": False}
    temporary = path.with_name(key + "." + uuid.uuid4().hex + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps({"key": key, "result": value,
                                         "result_sha256": digest(value)},
                                        ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    except (OSError, ValueError):
        state = "WRITE_FAILED"
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
    return value, {"key": key, "state": state, "reused": False}
