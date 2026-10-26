"""Official TSETMC index observations and current-only sector membership."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
import re
from datetime import date
from pathlib import Path
from typing import Any

from .archive import parse_market_date
from .financial_history import normalize
from .official_source_cache import cached_response

INDEX_IDS = {"major": ("32097828799138957", "شاخص کل"),
             "equal": ("67130298613737946", "شاخص کل (هم وزن)")}


async def fetch_index_context(*, symbol: str, ins_code: str, is_fund: bool,
                              as_of: date, last_completed_date: str | None,
                              getter=None, cache_root: Path | None = None) -> dict[str, Any]:
    if getter is None:
        from .tsetmc import _get
        getter = _get
    root = cache_root or Path("runtime/index_sources")

    async def index(code: str, expected_name: str) -> list[dict[str, Any]]:
        path = root / code / f"{as_of.isoformat()}.json"
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            raw = stored["responses"]
            encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != stored["sha256"]:
                raise ValueError("Index source cache integrity conflict")
        else:
            info, history = await asyncio.gather(
                getter(f"/Instrument/GetInstrumentInfo/{code}"),
                getter(f"/Index/GetIndexB2History/{code}"))
            raw = {"info": info, "history": history}
            encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
            stored = {"responses": raw, "sha256": hashlib.sha256(encoded).hexdigest(),
                      "source": "https://cdn.tsetmc.com/api", "captured_on": as_of.isoformat()}
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
            try:
                # Creating a hard link publishes the fully written file atomically
                # and fails if a concurrent analysis already published its copy.
                os.link(temporary, path)
            except FileExistsError:
                return await index(code, expected_name)
            finally:
                temporary.unlink(missing_ok=True)
        from .analyst_evidence import capture_cached
        capture_cached(f"https://cdn.tsetmc.com/api/index-evidence/{code}", raw)
        info = raw["info"].get("instrumentInfo") or {}
        if (str(info.get("insCode")) != code or str(info.get("yVal")) != "68"
                or normalize(info.get("lVal30")) != normalize(expected_name)):
            raise ValueError("Official index identity/name mismatch")
        rows = []
        for item in raw["history"].get("indexB2") or []:
            day = parse_market_date(item.get("dEven"))
            if (str(item.get("insCode")) == code and day is not None and
                    day <= as_of and last_completed_date is not None and
                    day.isoformat() <= last_completed_date):
                rows.append({"date": day.isoformat(), "close": item.get("xNivInuClMresIbs")})
        return rows

    bundle: dict[str, Any] = {"source": "TSETMC official Index API", "_verified_fetch": True,
                              "captured_on": as_of.isoformat(), "memberships": [],
                              "industry_indices": {}, "source_errors": []}
    for name, (code, title) in INDEX_IDS.items():
        try:
            bundle["major_index" if name == "major" else "equal_weight_index"] = await index(code, title)
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
            bundle["source_errors"].append(f"{name}: {exc}")
    if not is_fund:
        try:
            instrument = (await getter(f"/Instrument/GetInstrumentInfo/{ins_code}")).get("instrumentInfo") or {}
            sector = normalize((instrument.get("sector") or {}).get("lSecVal"))
            if not sector or parse_market_date(instrument.get("dEven")) != as_of:
                raise ValueError("Current dated sector identity unavailable")
            catalog, catalog_sha = await cached_response("/Index/GetIndexB1LastAll/AllIndexes/1",
                                                         as_of=as_of, getter=getter, root=root / "catalog")
            sector_code = normalize((instrument.get("sector") or {}).get("cSecVal", ""))
            matches = []
            for candidate in catalog.get("indexB1") or []:
                if not isinstance(candidate, dict):
                    continue
                title = normalize(candidate.get("lVal30", ""))
                coded = re.fullmatch(r"(\d{2})\s*-\s*(.+)", title)
                if coded and normalize(coded[2]) == sector and (not sector_code or coded[1] == sector_code):
                    matches.append(candidate)
            if len(matches) != 1:
                raise ValueError("Unambiguous official industry index unavailable")
            chosen = matches[0]
            industry_rows = await index(str(chosen["insCode"]), chosen["lVal30"])
            bundle["industry_indices"][sector] = industry_rows
            bundle["industry_identity"] = {"ins_code": str(chosen["insCode"]),
                                            "official_name": chosen["lVal30"], "sector_code": sector_code,
                                            "catalog_sha256": catalog_sha}
            bundle["memberships"] = [{"symbol": symbol, "industry": sector,
                                       "effective_from": as_of.isoformat(), "effective_to": as_of.isoformat()}]
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
            bundle["source_errors"].append(f"industry: {exc}")
    return bundle
