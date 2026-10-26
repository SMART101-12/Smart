"""Dated summaries of verified observations; windows count trading sessions."""
from __future__ import annotations


def horizon_summaries(verified_rows: list[dict]) -> dict:
    result = {}
    for size in (20, 60, 120, 250):
        rows = verified_rows[-size:]
        first, last = (rows[0], rows[-1]) if rows else ({}, {})
        result[str(size)] = {
            "requested_sessions": size, "observations": len(rows),
            "status": "SUFFICIENT_OBSERVATIONS" if len(rows) == size else "INSUFFICIENT_DATA",
            "from_date": first.get("source_date"), "to_date": last.get("source_date"),
            "low": min((r["low"] for r in rows), default=None),
            "high": max((r["high"] for r in rows), default=None),
            "first_close": first.get("close"), "last_close": last.get("close"),
            "observed_return_pct": (last["close"] / first["close"] - 1) * 100 if rows else None,
            "calendar_continuity": "UNVERIFIED", "price_adjustment": "UNVERIFIED",
            "method": "verified_completed_session_observations",
            "close_bases": sorted({r.get("close_basis", "provided_close") for r in rows}),
        }
    return result
