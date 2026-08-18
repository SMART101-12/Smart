"""Validate and partition one TSETMC historical series into Jalali months."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "runtime" / "market_raw" / "history"
OUT_ROOT = ROOT / "runtime" / "market_processed" / "history"
VALID_ROOT = ROOT / "runtime" / "market_processed" / "history_validation"


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    jy = 979 if gy > 1600 else 0
    gy2 = gy - 1600 if gy > 1600 else gy - 621
    gy3 = gy2 + 1 if gm > 2 else gy2
    days = 365 * gy2 + (gy3 + 3) // 4 - (gy3 + 99) // 100 + (gy3 + 399) // 400 - 80 + gd + g_days[gm - 1]
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        days += 1
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


def safe_symbol(symbol: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", symbol).rstrip(" .") or "UNKNOWN"


def load_payload(symbol: str) -> tuple[Path, dict, list[dict]]:
    folder = RAW_ROOT / safe_symbol(symbol)
    candidates = sorted(folder.glob("*.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No raw history JSON found for symbol={symbol}")
    source = candidates[0]
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"No records found in {source}")
    return source, payload, records


def normalize(records: list[dict]) -> tuple[list[dict], dict]:
    valid, invalid_dates, duplicate_dates = [], [], []
    seen: set[str] = set()
    for row in records:
        date_text = str(row.get("date", ""))
        try:
            parsed = dt.datetime.strptime(date_text, "%Y%m%d").date()
        except ValueError:
            invalid_dates.append(date_text)
            continue
        if date_text in seen:
            duplicate_dates.append(date_text)
            continue
        seen.add(date_text)
        item = dict(row)
        item["date_gregorian"] = parsed.isoformat()
        jy, jm, jd = gregorian_to_jalali(parsed.year, parsed.month, parsed.day)
        item["date_jalali"] = f"{jy:04d}-{jm:02d}-{jd:02d}"
        item["jalali_year"] = jy
        item["jalali_month"] = jm
        valid.append(item)
    valid.sort(key=lambda r: r["date_gregorian"])
    large_gaps = []
    for a, b in zip(valid, valid[1:]):
        delta = (dt.date.fromisoformat(b["date_gregorian"]) - dt.date.fromisoformat(a["date_gregorian"])).days
        if delta > 7:
            large_gaps.append({"from": a["date_gregorian"], "to": b["date_gregorian"], "calendar_days": delta})
    return valid, {
        "source_record_count": len(records),
        "valid_record_count": len(valid),
        "invalid_date_count": len(invalid_dates),
        "invalid_dates_sample": invalid_dates[:20],
        "duplicate_date_count": len(duplicate_dates),
        "duplicate_dates_sample": duplicate_dates[:20],
        "large_gap_count": len(large_gaps),
        "large_gaps_sample": large_gaps[:20],
        "status": "ok" if not invalid_dates and not duplicate_dates else "warning",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=False)
    parser.add_argument("--symbol-hex", required=False)
    args = parser.parse_args()
    if args.symbol_hex:
        try:
            symbol = bytes.fromhex(args.symbol_hex).decode("utf-8")
        except ValueError as exc:
            raise RuntimeError("Invalid UTF-8 hex symbol") from exc
    elif args.symbol:
        symbol = args.symbol.strip()
    else:
        raise RuntimeError("A symbol is required")

    source, payload, records = load_payload(symbol)
    valid, validation = normalize(records)
    if not valid:
        raise RuntimeError("No valid historical records after validation")

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in valid:
        groups[f"{row['jalali_year']:04d}-{row['jalali_month']:02d}"].append(row)

    out_folder = OUT_ROOT / safe_symbol(symbol)
    validation_folder = VALID_ROOT / safe_symbol(symbol)
    out_folder.mkdir(parents=True, exist_ok=True)
    validation_folder.mkdir(parents=True, exist_ok=True)

    month_summaries = []
    for month_key, month_rows in sorted(groups.items()):
        out_payload = {
            "source": "TSETMC",
            "source_type": "daily_history_monthly_partition",
            "symbol": payload.get("symbol", symbol),
            "requested_symbol": payload.get("requested_symbol", symbol),
            "ins_code": payload.get("ins_code"),
            "period": month_key,
            "record_count": len(month_rows),
            "first_date_gregorian": month_rows[0]["date_gregorian"],
            "last_date_gregorian": month_rows[-1]["date_gregorian"],
            "records": month_rows,
        }
        (out_folder / f"{month_key}.json").write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        month_summaries.append({
            "period": month_key,
            "record_count": len(month_rows),
            "first_date_gregorian": month_rows[0]["date_gregorian"],
            "last_date_gregorian": month_rows[-1]["date_gregorian"],
        })

    summary = {
        "symbol": payload.get("symbol", symbol),
        "requested_symbol": symbol,
        "ins_code": payload.get("ins_code"),
        "source_file": str(source.relative_to(ROOT)).replace("\\", "/"),
        "processed_at": dt.datetime.now().astimezone().isoformat(),
        "overall": validation,
        "month_count": len(month_summaries),
        "months": month_summaries,
    }
    (validation_folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for month in month_summaries:
        month_rows = groups[month["period"]]
        (validation_folder / f"{month['period']}.json").write_text(json.dumps({
            "symbol": payload.get("symbol", symbol),
            "period": month["period"],
            "record_count": len(month_rows),
            "first_date_gregorian": month_rows[0]["date_gregorian"],
            "last_date_gregorian": month_rows[-1]["date_gregorian"],
            "status": "ok",
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Symbol: {symbol}")
    print(f"Source: {source}")
    print(f"Raw records: {validation['source_record_count']}")
    print(f"Valid records: {validation['valid_record_count']}")
    print(f"Months created: {len(month_summaries)}")
    print(f"Duplicate dates: {validation['duplicate_date_count']}")
    print(f"Invalid dates: {validation['invalid_date_count']}")
    print(f"Large gaps (>7 days): {validation['large_gap_count']}")
    print(f"Output: {out_folder}")
    print(f"Validation: {validation_folder / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
