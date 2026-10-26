"""Publish complete JSON documents without exposing a partially written file."""
from __future__ import annotations

import contextlib
import json
import time
import uuid
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(encoded, encoding="utf-8")
        # A Windows polling reader may briefly hold the destination open.
        for attempt in range(10):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(.03)
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
