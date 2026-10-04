"""Keep observed client-type trading separate from volume-price proxies."""
from __future__ import annotations

from datetime import date
from statistics import mean
from math import isfinite
from typing import Any

from .archive import deduplicate_rows, parse_market_date


def analyze_flow(history: list[dict[str, Any]], *, symbol: str, as_of: date,
                 client_type: dict[str, Any] | None = None) -> dict[str, Any]:
    rows, _ = deduplicate_rows(history, symbol=symbol)
    rows = [r for r in rows if parse_market_date(r["source_date"]) <= as_of
            and type(r.get("volume")) in (int, float) and r["volume"] >= 0
            and isfinite(r["volume"])
            and type(r.get("close")) in (int, float) and isfinite(r["close"]) and r["close"] > 0]
    proxy = {"status": "UNAVAILABLE", "signal": "UNAVAILABLE", "as_of": None}
    if len(rows) >= 21:
        baseline = mean(r["volume"] for r in rows[-21:-1])
        recent = mean(r["volume"] for r in rows[-6:-1])
        last = rows[-1]
        if baseline > 0 and recent > 0:
            ratio20 = last["volume"] / baseline
            ratio5 = last["volume"] / recent
            rising = last["close"] > rows[-2]["close"]
            falling = last["close"] < rows[-2]["close"]
            proxy = {"status": "SUCCESS", "as_of": last["source_date"],
                     "signal": "BULLISH" if ratio20 >= 1.2 and rising else
                               "BEARISH" if ratio20 >= 1.2 and falling else "NEUTRAL",
                     "volume_ratio_5": round(ratio5, 3),
                     "volume_ratio_20": round(ratio20, 3),
                     "provenance": "calculated_from_OHLCV_not_client_type"}
    observation = client_type or {}
    day = parse_market_date(observation.get("date"))
    buy, sell = observation.get("buy_individual_volume"), observation.get("sell_individual_volume")
    count_buy, count_sell = observation.get("buy_individual_count"), observation.get("sell_individual_count")
    observed = {"status": "UNAVAILABLE", "signal": "UNAVAILABLE", "as_of": None,
                "reason": "dated_client_type_volume_unavailable"}
    if (observation.get("source") == "TSETMC ClientType" and day is not None and day <= as_of
            and 0 <= (as_of - day).days <= 5
            and type(buy) in (int, float) and type(sell) in (int, float)
            and isfinite(buy) and isfinite(sell) and buy >= 0 and sell >= 0 and buy + sell > 0):
        net = buy - sell
        power = ((buy / count_buy) / (sell / count_sell)
                 if all(type(v) in (int, float) and isfinite(v) and v > 0 for v in (buy, sell, count_buy, count_sell)) else None)
        observed = {"status": "SUCCESS", "signal": "BULLISH" if net > 0 else "BEARISH" if net < 0 else "NEUTRAL",
                    "as_of": day.isoformat(), "net_individual_volume": net,
                    "individual_buy_power": round(power, 3) if power is not None else None,
                    "source": observation["source"], "source_sha256": observation.get("source_sha256"),
                    "ins_code": observation.get("ins_code")}
    conflicts = []
    corporate = [observation.get(k) for k in ("buy_corporate_volume", "sell_corporate_volume")]
    if observed["status"] == "SUCCESS" and "buy_corporate_volume" in observation and not all(
            type(v) in (int, float) and isfinite(v) and v >= 0 for v in corporate):
        conflicts.append("client_type_corporate_volume_unavailable")
    elif observed["status"] == "SUCCESS" and rows and all(
            type(v) in (int, float) and isfinite(v) and v >= 0 for v in corporate):
        total_buy = buy + corporate[0]
        total_sell = sell + corporate[1]
        volume = rows[-1]["volume"]
        observed["reported_total_buy_volume"] = total_buy
        observed["reported_total_sell_volume"] = total_sell
        if abs(total_buy - total_sell) > max(1, total_buy * 1e-6):
            conflicts.append("client_type_buy_sell_totals_differ")
        if day == parse_market_date(rows[-1]["source_date"]) and abs(total_buy - volume) > max(1, volume * 1e-6):
            conflicts.append("client_type_and_OHLCV_volume_mismatch")
    if observed["status"] == "SUCCESS" and proxy["status"] == "SUCCESS":
        if observed["signal"] == "BEARISH" and proxy["signal"] == "BULLISH":
            conflicts.append("rising_price_volume_with_individual_outflow")
        if observed["signal"] == "BULLISH" and proxy["signal"] == "BEARISH":
            conflicts.append("falling_price_volume_with_individual_inflow")
        if observed["as_of"] != proxy["as_of"]:
            conflicts.append("client_type_and_price_sessions_differ")
    return {"status": "CONFLICTING" if conflicts else
            "SUCCESS" if observed["status"] == "SUCCESS" else
            "PARTIAL" if proxy["status"] == "SUCCESS" else "UNAVAILABLE",
            "signal": "CONFLICTING" if conflicts else observed["signal"],
            "observed_client_type": observed, "price_volume_proxy": proxy,
            "conflicts": conflicts}
