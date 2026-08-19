from __future__ import annotations

from typing import Any


class ProcessingService:
    """Pure processing boundary; accepts validated records only."""

    def process(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # V2 intentionally starts with a no-op transformation. Indicators and
        # feature engineering will be added without coupling to acquisition.
        return [dict(record) for record in records]
