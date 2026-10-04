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
               "buy_corporate_volume": "buy_N_Volume", "sell_corporate_volume": "sell_N_Volume"}
    values = {}
    for field, source_field in mapping.items():
        value = row.get(source_field)
        values[field] = value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    if any(values[k] is None for k in ("buy_individual_volume", "sell_individual_volume")):
        return {"status": "UNAVAILABLE", "reason": "client_type_volume_missing", "source_sha256": signature}
    return {"status": "SUCCESS", "date": target.isoformat(), "source": "TSETMC ClientType",
            "ins_code": str(ins_code), "endpoint": path, "source_sha256": signature, **values}
