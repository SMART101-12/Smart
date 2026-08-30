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
            def _value(*keys: str) -> Any:
                zero_value: Any = None
                for key in keys:
                    value = record.get(key)
                    if value not in (None, ""):
                        try:
                            if float(value) == 0:
                                if zero_value is None:
                                    zero_value = value
                                continue
                        except (TypeError, ValueError):
                            pass
                        return value
                return zero_value

            processed["processing"] = {
                "status": "PROCESSED",
                "derived": {
                    "close": _value("pClosing", "priceClosing", "close", "pcl", "pDrCotVal"),
                    "last_price": _value("pDrCotVal", "last_price", "last", "pl"),
                    "price_change": _value("priceChange", "price_change", "pc"),
                    "volume": _value("qTotTran5J", "volume", "tvol", "qtj"),
                    "trade_count": _value("zTotTran", "trades", "tno"),
                    "trade_value": _value("qTotCap", "value", "tval", "qtc"),
                },
            }

            output.append(processed)

        return output
