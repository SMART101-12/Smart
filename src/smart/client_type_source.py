"""Select observed client-type evidence from the exact completed price session."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from .archive import parse_market_date
from .official_source_cache import cached_response


async def fetch_client_type_evidence(*, ins_code: str, price_date: str | None,
                                     as_of: date, getter=None, cache_root: Path | None = None) -> dict:
    target = parse_market_date(price_date)
    if target is None or target > as_of or not str(ins_code).isdigit():
        return {"status": "UNAVAILABLE", "reason": "completed_price_session_unavailable"}
    if getter is None:
        from .tsetmc import _get
        getter = _get
    path = f"/ClientType/GetClientTypeHistory/{ins_code}"
    raw, signature = await cached_response(path, as_of=as_of, getter=getter,
                                            root=cache_root or Path("runtime/client_type_sources"))
    rows = raw.get("clientType")
    if not isinstance(rows, list):
        raise ValueError("Invalid dated ClientType response")
    matches = {json.dumps(row, sort_keys=True): row for row in rows if isinstance(row, dict)
               and str(row.get("insCode")) == str(ins_code)
               and parse_market_date(row.get("recDate")) == target}
    if len(matches) != 1:
        return {"status": "UNAVAILABLE", "reason": "client_type_session_missing_or_conflicting",
                "expected_date": target.isoformat(), "source_sha256": signature}
    row = next(iter(matches.values()))
    mapping = {"buy_individual_volume": "buy_I_Volume", "sell_individual_volume": "sell_I_Volume",
               "buy_individual_count": "buy_I_Count", "sell_individual_count": "sell_I_Count",
               "buy_corporate_volume": "buy_N_Volume", "sell_corporate_volume": "sell_N_Volume",
               "buy_corporate_count": "buy_N_Count", "sell_corporate_count": "sell_N_Count",
               "buy_individual_value": "buy_I_Value", "sell_individual_value": "sell_I_Value",
               "buy_corporate_value": "buy_N_Value", "sell_corporate_value": "sell_N_Value"}
    values = {}
    for field, source_field in mapping.items():
        value = row.get(source_field)
        values[field] = value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    if any(values[k] is None for k in ("buy_individual_volume", "sell_individual_volume")):
        return {"status": "UNAVAILABLE", "reason": "client_type_volume_missing", "source_sha256": signature}
    # Preserve dated history from the same response; never substitute a later session.
    grouped = {}
    for item in rows:
        if not isinstance(item, dict) or str(item.get("insCode")) != str(ins_code):
            continue
        day = parse_market_date(item.get("recDate"))
        if day is not None and day <= target:
            grouped.setdefault(day.isoformat(), {})[json.dumps(item, sort_keys=True)] = item
    history, conflicting = [], []
    for day, variants in sorted(grouped.items()):
        if len(variants) != 1:
            conflicting.append(day)
            continue
        item = next(iter(variants.values()))
        history.append({"date": day, **{field: item.get(source) if type(item.get(source)) in (int, float)
            and math.isfinite(item[source]) and item[source] >= 0 else None
            for field, source in mapping.items()}})
    return {"status": "SUCCESS", "date": target.isoformat(), "source": "TSETMC ClientType",
            "ins_code": str(ins_code), "endpoint": path, "source_sha256": signature,
            "history": history, "conflicting_dates": conflicting, **values}
