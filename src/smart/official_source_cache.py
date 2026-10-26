"""Immutable response snapshots for read-only official TSETMC endpoints."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path


async def cached_response(path: str, *, as_of: date, getter, root: Path) -> tuple[dict, str]:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Official source requires a relative API path")
    key = hashlib.sha256(path.encode("utf-8")).hexdigest()
    target = root / key / (as_of.isoformat() + ".json")
    if target.exists():
        saved = json.loads(target.read_text(encoding="utf-8"))
        raw = saved["response"]
        signature = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if saved["path"] != path or saved["as_of"] != as_of.isoformat() or signature != saved["sha256"]:
            raise ValueError("Official source cache integrity conflict")
        from .analyst_evidence import capture_cached
        capture_cached("https://cdn.tsetmc.com/api" + path, raw)
        return raw, signature
    raw = await getter(path)
    if not isinstance(raw, dict):
        raise ValueError("Official response must be an object")
    signature = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    saved = {"path": path, "as_of": as_of.isoformat(), "response": raw, "sha256": signature,
             "source": "TSETMC official API", "retrieved_at": datetime.now(timezone.utc).isoformat()}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix("." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    try:
        os.link(temporary, target)
    except FileExistsError:
        return await cached_response(path, as_of=as_of, getter=getter, root=root)
    finally:
        temporary.unlink(missing_ok=True)
    return raw, signature
