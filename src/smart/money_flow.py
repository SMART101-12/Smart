"""Dated ownership transfer; monetary proxies are never actual group trade values."""
from math import isfinite

from .archive import parse_market_date


def valid(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


def analyze_money_flow(rows, observation):
    bars = {r["source_date"]: r for r in rows}
    target = parse_market_date(observation.get("date"))
    result = {"status": "UNAVAILABLE", "latest": None, "history": [], "windows": {},
              "unit": "IRR", "method": "observed_group_values_with_separate_vwap_estimate",
              "value_quality": "ESTIMATED", "issues": [],
              "source": observation.get("source"), "source_sha256": observation.get("source_sha256"),
              "ins_code": observation.get("ins_code"),
              "interpretation": "جریان حقیقی و حقوقی دو سمت تغییر مالکیت هستند و دو تأیید مستقل نیستند. مبلغ واقعی از ارزش معاملات هر گروه و مبلغ برآوردی از حجم ضرب‌در میانگین قیمت روز محاسبه می‌شود؛ این داده به‌تنهایی سیگنال ورود یا خروج نیست."}
    if observation.get("source") != "TSETMC ClientType" or target is None:
        return result
    candidates = observation.get("history") or [observation]
    grouped = {}
    for item in candidates:
        day = parse_market_date(item.get("date"))
        if day and day <= target:
            grouped.setdefault(day.isoformat(), []).append(item)
    for day, items in sorted(grouped.items()):
        if len(items) != 1:
            result["issues"].append({"date": day, "reason": "duplicate_client_session"})
            continue
        item, bar = items[0], bars.get(day)
        volumes = [item.get(k) for k in ("buy_individual_volume", "sell_individual_volume",
                                            "buy_corporate_volume", "sell_corporate_volume")]
        if not bar or not all(valid(v) for v in volumes):
            continue
        buy, sell, cbuy, csell = volumes
        total = buy + cbuy
        volume = bar.get("volume")
        if not valid(volume) or volume <= 0 or abs(total - sell - csell) > max(1, total * 1e-6) or abs(total - volume) > max(1, volume * 1e-6):
            result["issues"].append({"date": day, "reason": "volume_totals_mismatch"})
            continue
        value = bar.get("value")
        vwap = value / volume if valid(value) and value > 0 else None
        low, high = bar.get("low"), bar.get("high")
        if vwap is not None and (not valid(low) or not valid(high) or vwap < low or vwap > high):
            result["issues"].append({"date": day, "reason": "turnover_price_outside_traded_range"})
            vwap = None
        net = buy - sell
        record = {"date": day, "net_individual_volume": net, "net_corporate_volume": cbuy - csell,
                  "net_individual_value_estimate": net * vwap if vwap else None,
                  "net_corporate_value_estimate": (cbuy - csell) * vwap if vwap else None,
                  "net_volume_pct": net / volume * 100, "vwap": vwap,
                  "turnover": value if vwap else None,
                  "individual_buy_volume": buy, "individual_sell_volume": sell,
                  "corporate_buy_volume": cbuy, "corporate_sell_volume": csell}
        for group, bv, sv in (("individual", buy, sell), ("corporate", cbuy, csell)):
            bc, sc = item.get("buy_" + group + "_count"), item.get("sell_" + group + "_count")
            per_buy = bv / bc if valid(bc) and bc > 0 else None
            per_sell = sv / sc if valid(sc) and sc > 0 else None
            record[group + "_buy_per_capita_volume"] = per_buy
            record[group + "_sell_per_capita_volume"] = per_sell
            record[group + "_buy_power"] = per_buy / per_sell if per_buy is not None and per_sell else None
            record[group + "_buy_per_capita_value_estimate"] = per_buy * vwap if per_buy is not None and vwap else None
            record[group + "_sell_per_capita_value_estimate"] = per_sell * vwap if per_sell is not None and vwap else None
        cash = [item.get(k) for k in ("buy_individual_value", "sell_individual_value",
                                     "buy_corporate_value", "sell_corporate_value")]
        cash_valid = all(valid(v) for v in cash)
        if cash_valid:
            ib, iss, nb, ns = cash
            total_value = ib + nb
            cash_valid = total_value > 0 and abs(total_value - iss - ns) <= max(1, total_value * 1e-6)
            if valid(value) and value > 0:
                cash_valid = cash_valid and abs(total_value - value) <= max(1, value * 1e-6)
            if not cash_valid:
                result["issues"].append({"date": day, "reason": "client_value_totals_mismatch"})
        record["net_individual_value"] = cash[0] - cash[1] if cash_valid else None
        record["net_corporate_value"] = cash[2] - cash[3] if cash_valid else None
        record["value_quality"] = "OBSERVED" if cash_valid else "ESTIMATED"
        for group, offset in (("individual", 0), ("corporate", 2)):
            bc, sc = item.get("buy_" + group + "_count"), item.get("sell_" + group + "_count")
            pb = cash[offset] / bc if cash_valid and valid(bc) and bc > 0 else None
            ps = cash[offset+1] / sc if cash_valid and valid(sc) and sc > 0 else None
            record[group + "_buy_per_capita_value"] = pb
            record[group + "_sell_per_capita_value"] = ps
            record[group + "_value_buy_power"] = pb / ps if pb is not None and ps else None
        result["history"].append(record)
    target_text = target.isoformat()
    result["latest"] = next((r for r in result["history"] if r["date"] == target_text), None)
    result["status"] = "SUCCESS" if result["latest"] else "UNAVAILABLE"
    if result["latest"]:
        result["value_quality"] = result["latest"]["value_quality"]
    expected = sorted(day for day in bars if day <= target_text)
    if result["latest"] and len(expected) >= 2:
        change = bars[expected[-1]]["close"] - bars[expected[-2]]["close"]
        net = result["latest"].get("net_individual_value")
        if net is None:
            net = result["latest"]["net_individual_volume"]
        result["price_flow_context"] = (
            "رشد قیمت همراه خرید خالص حقیقی؛ هم‌جهتی تقاضا و قیمت، نیازمند بررسی تداوم و مقاومت‌ها."
            if change > 0 and net > 0 else
            "رشد قیمت همراه فروش خالص حقیقی؛ واگرایی جریان حقیقی و قیمت، نیازمند بررسی نقش حقوقی."
            if change > 0 and net < 0 else
            "افت قیمت همراه خرید خالص حقیقی؛ خرید حقیقی هنوز با تأیید روند قیمت همراه نیست."
            if change < 0 and net > 0 else
            "افت قیمت همراه فروش خالص حقیقی؛ هم‌جهتی فشار فروش و قیمت."
            if change < 0 and net < 0 else "قیمت یا جریان خالص بدون جهت مشخص است.")
    indexed = {r["date"]: r for r in result["history"]}
    for count in (1, 5, 20):
        dates = expected[-count:]
        available = [indexed[d] for d in dates if d in indexed]
        complete = len(dates) == count and len(available) == count
        values_complete = complete and all(r["net_individual_value_estimate"] is not None for r in available)
        result["windows"][str(count)] = {"required": count, "available": len(available),
            "status": "COMPLETE" if complete else "INSUFFICIENT",
            "from_date": dates[0] if dates else None, "to_date": dates[-1] if dates else None,
            "net_individual_volume": sum(r["net_individual_volume"] for r in available) if complete else None,
            "net_individual_value_estimate": sum(r["net_individual_value_estimate"] for r in available) if values_complete else None,
            "net_individual_value": sum(r["net_individual_value"] for r in available)
                if complete and all(r["net_individual_value"] is not None for r in available) else None,
            "inflow_sessions": sum(r["net_individual_volume"] > 0 for r in available) if complete else None}
    return result
