"""Repository-first async TSETMC history for the existing dashboard engine."""
from __future__ import annotations

from datetime import date, timedelta

from .financial_history import HistoricalDataRepository, now, number, settings
from .incremental import expected_market_dates, parse_market_date


def validate_market_row(row, requested_date=None):
    if not isinstance(row, dict):
        raise ValueError("Invalid market row schema")
    day = parse_market_date(row.get("dEven"))
    if day is None or day > date.today() or requested_date and day != requested_date:
        raise ValueError("Invalid or mismatched market date")
    for field in ("pClosing", "pDrCotVal", "qTotTran5J", "qTotCap", "zTotTran",
                  "priceFirst", "priceMax", "priceMin"):
        value = number(row.get(field))
        if value is not None and value < 0:
            raise ValueError(f"Negative market field: {field}")
    closing = number(row.get("pClosing"))
    if closing is None or closing <= 0:
        raise ValueError("No verified closing price")
    high, low = number(row.get("priceMax")), number(row.get("priceMin"))
    if high is not None and low is not None and high < low:
        raise ValueError("Invalid market high/low")
    return dict(row, dEven=int(day.strftime("%Y%m%d")))


async def repository_history(ins_code, fetch, top=0, repository=None, force=False):
    repo = repository or HistoricalDataRepository()
    identity = str(ins_code)
    local = []
    stored = repo.history(identity, "tsetmc")
    for symbol in repo.instrument_symbols(identity):
        stored.extend(repo.history(symbol, "tsetmc"))
    for item in stored:
        try:
            local.append(validate_market_row(item["payload"]))
        except (ValueError, TypeError):
            continue
    local = list({r["dEven"]: r for r in local}.values())
    local.sort(key=lambda r: r["dEven"], reverse=True)
    state = repo.state(identity, "TSETMC")
    if not force and repo.fresh(identity, "TSETMC", settings()["sync_ttl_seconds"]):
        return local[:top] if top else local
    result = {"symbol": identity, "source": "TSETMC", "status": "SUCCESS",
              "local_records": len(local), "records_received": 0, "inserted": 0,
              "updated": 0, "rejected": [], "unresolved_dates": [],
              "last_sync_date": state.get("last_sync_date")}
    fetched = []
    try:
        if not local:
            data = await fetch(f"/ClosingPrice/GetClosingPriceDailyList/{identity}/0")
            rows = data.get("closingPriceDaily")
            if not isinstance(rows, list):
                raise ValueError("Invalid TSETMC history response")
            result["records_received"] = len(rows)
            for row in rows:
                try:
                    fetched.append(validate_market_row(row))
                except (ValueError, TypeError) as exc:
                    result["rejected"].append({"error": str(exc), "date": row.get("dEven") if isinstance(row, dict) else None})
        else:
            latest = max(parse_market_date(r["dEven"]) for r in local)
            candidates = set(expected_market_dates(latest + timedelta(days=1), date.today()))
            candidates.update(d for raw in state.get("unresolved_dates", []) if (d := parse_market_date(raw)))
            dates = sorted(candidates)
            # Bounded catch-up; unfinished dates stay explicit for the next sync.
            result["unresolved_dates"] = [d.isoformat() for d in dates[400:]]
            for day in dates[:400]:
                try:
                    data = await fetch(f"/ClosingPrice/GetClosingPriceDaily/{identity}/{day:%Y%m%d}")
                    row = data.get("closingPriceDaily")
                    if isinstance(row, list):
                        row = row[0] if len(row) == 1 else None
                    result["records_received"] += 1 if row is not None else 0
                    fetched.append(validate_market_row(row, day))
                except Exception as exc:
                    result["unresolved_dates"].append(day.isoformat())
                    result["rejected"].append({"date": day.isoformat(), "error": str(exc)})
        if fetched:
            from datetime import datetime, timezone
            counts = repo.save_daily_history_incremental(identity, "tsetmc", datetime.now(timezone.utc), fetched)
            result.update(counts)
        if result["rejected"] or result["unresolved_dates"]:
            result["status"] = "PARTIAL"
        else:
            result["last_sync_date"] = now()
    except Exception as exc:
        result.update(status="SOURCE_UNAVAILABLE", error=str(exc))
    repo.record_sync(identity, "TSETMC", result)
    merged = {r["dEven"]: r for r in [*local, *fetched]}
    rows = [merged[d] for d in sorted(merged, reverse=True)]
    if not rows and result["status"] == "SOURCE_UNAVAILABLE":
        raise RuntimeError("TSETMC unavailable; insufficient verified local data")
    return rows[:top] if top else rows
