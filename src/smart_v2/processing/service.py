from __future__ import annotations

from typing import Any


class ProcessingService:
    """Process validated market records without touching acquisition."""

    def process(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []

        for item in records:
            record = dict(item.get("record", {}))

            processed = dict(item)
            processed["record"] = record
            processed["processing"] = {
                "status": "PROCESSED",
                "derived": {
                    "close": record.get("pClosing"),
                    "last_price": record.get("pDrCotVal"),
                    "price_change": record.get("priceChange"),
                    "volume": record.get("qTotTran5J"),
                    "trade_count": record.get("zTotTran"),
                    "trade_value": record.get("qTotCap"),
                },
            }

            output.append(processed)

        return output
