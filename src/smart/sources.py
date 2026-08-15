"""Market-source adapters.

The first release keeps adapters isolated so a source can be replaced without
changing the scanner. No source is treated as authoritative until validation
passes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


class SourceError(RuntimeError):
    pass


async def fetch_json(url: str, *, timeout: float = 10.0) -> Any:
    """Fetch a JSON endpoint with a short timeout and explicit error handling."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "SMART/0.1"})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceError(f"source request failed: {url}") from exc


def source_status(name: str, *, url: str, available: bool, detail: str = "") -> dict[str, Any]:
    return {
        "source": name,
        "url": url,
        "available": available,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "detail": detail,
    }
