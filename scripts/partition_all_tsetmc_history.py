"""Validate and partition all configured TSETMC history series by InsCode."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "runtime" / "market_raw" / "history"
UNIVERSE_ROOT = ROOT / "runtime" / "market_raw" / "history_universe"
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


def load_latest_universe() -> list[dict]:
    files = sorted(UNIVERSE_ROOT.glob("*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(f"No history universe found under {UNIVERSE_ROOT}")
    payload = json.loads(files[0].read_text(encoding="utf-8-sig"))
    rows = payload.get("symbols")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"No symbols found in {files[0]}")
    return [r for r in rows if r.get("ins_code") and r.get("status") == "ok"]


def build_raw_index() -> dict[int, tuple[Path, dict]]:
    index: dict[int, tuple[Path, dict]] = {}
    for path in RAW_ROOT.glob("*/2026-08-18.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            ins_code = int(payload.get("ins_code"))
            if ins_code:
                index[ins_code] = (path, payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    if not index:
        for path in RAW_ROOT.glob("*/*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                ins_code = int(payload.get("ins_code"))
                if ins_code:
                    index[ins_code] = (path, payload)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    return index


def normalize(records: list[dict]) -> tuple[list[dict], dict]:
    valid: list[dict] = []
    invalid_dates: list[str] = []
    duplicate_dates: list[str] = []
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
        "duplicate_date_count": len(duplicate_dates),
        "invalid_dates_sample": invalid_dates[:20],
        "duplicate_dates_sample": duplicate_dates[:20],
        "large_gap_count": len(large_gaps),
        "large_gaps_sample": large_gaps[:20],
        "status": "ok" if not invalid_dates and not duplicate_dates else "warning",
    }


def process_symbol(entry: dict, raw_index: dict[int, tuple[Path, dict]]) -> dict:
    ins_code = int(entry["ins_code"])
    symbol = str(entry.get("resolved_symbol") or entry.get("symbol") or ins_code)
    if ins_code not in raw_index:
        return {"symbol": symbol, "ins_code": ins_code, "status": "error", "error": "raw history not found"}
    source, payload = raw_index[ins_code]
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return {"symbol": symbol, "ins_code": ins_code, "status": "error", "error": "no records"}
    valid, validation = normalize(records)
    if not valid:
        return {"symbol": symbol, "ins_code": ins_code, "status": "error", "error": "no valid records", "validation": validation}

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in valid:
        groups[f"{row['jalali_year']:04d}-{row['jalali_month']:02d}"].append(row)

    out_folder = OUT_ROOT / str(ins_code)
    validation_folder = VALID_ROOT / str(ins_code)
    out_folder.mkdir(parents=True, exist_ok=True)
    validation_folder.mkdir(parents=True, exist_ok=True)

    months = []
    for month_key, rows in sorted(groups.items()):
        out_payload = {
            "source": "TSETMC",
            "source_type": "daily_history_monthly_partition",
            "symbol": payload.get("symbol", symbol),
            "requested_symbol": payload.get("requested_symbol", symbol),
            "ins_code": ins_code,
            "period": month_key,
            "record_count": len(rows),
            "first_date_gregorian": rows[0]["date_gregorian"],
            "last_date_gregorian": rows[-1]["date_gregorian"],
            "records": rows,
        }
        (out_folder / f"{month_key}.json").write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        months.append({"period": month_key, "record_count": len(rows), "first_date_gregorian": rows[0]["date_gregorian"], "last_date_gregorian": rows[-1]["date_gregorian"]})

    summary = {
        "symbol": symbol,
        "ins_code": ins_code,
        "source_file": str(source.relative_to(ROOT)).replace("\\", "/"),
        "processed_at": dt.datetime.now().astimezone().isoformat(),
        "overall": validation,
        "month_count": len(months),
        "months": months,
    }
    (validation_folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"symbol": symbol, "ins_code": ins_code, "status": "ok", "records": len(valid), "months": len(months), "large_gaps": validation["large_gap_count"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    universe = load_latest_universe()
    if args.limit > 0:
        universe = universe[:args.limit]
    raw_index = build_raw_index()
    print(f"Universe symbols: {len(universe)}")
    print(f"Raw history series indexed: {len(raw_index)}")

    results = []
    for i, entry in enumerate(universe, 1):
        print(f"[{i}/{len(universe)}] InsCode={entry['ins_code']} symbol={entry.get('symbol','')}")
        try:
            result = process_symbol(entry, raw_index)
        except Exception as exc:
            result = {"symbol": entry.get("symbol", ""), "ins_code": entry["ins_code"], "status": "error", "error": str(exc)}
        results.append(result)
        if result["status"] == "ok":
            print(f"  OK: {result['records']} records, {result['months']} months")
        else:
            print(f"  ERROR: {result['error']}")

    report = {
        "source": "SMART/TSETMC",
        "processed_at": dt.datetime.now().astimezone().isoformat(),
        "universe_count": len(universe),
        "success_count": sum(r["status"] == "ok" for r in results),
        "error_count": sum(r["status"] != "ok" for r in results),
        "results": results,
    }
    report_path = VALID_ROOT / "all_symbols_summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completed: {report['success_count']}/{report['universe_count']} symbols")
    print(f"Report: {report_path}")
    return 0 if report["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
