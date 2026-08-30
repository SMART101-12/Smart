"""Canonical daily-history archiving, validation and safe cleanup helpers.

The SMART repository contains several historical layouts accumulated over
different iterations of the project.  This module provides one small,
deterministic contract for new data without rewriting or deleting the raw
evidence.  Raw rows can be retained in ``runtime/market_raw`` while the
canonical archive is written to a derived directory such as
``runtime/market_processed/canonical``.

The functions are intentionally dependency-light so they can be used from a
scheduled job and from tests on a clean installation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DATE_KEYS = ("date", "dEven", "market_date", "source_date")
ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "lVal18AFC", "lva", "lVal18"),
    "ins_code": ("ins_code", "insCode", "insID"),
    "open": ("open", "pOpen", "pFirst", "priceFirst", "pf"),
    "high": ("high", "pHigh", "pMax", "priceMax", "pmax", "pmx"),
    "low": ("low", "pLow", "pMin", "priceMin", "pmin", "pmn"),
    "close": (
        "close",
        "pClosing",
        "priceClosing",
        "pcl",
        "pDrCotVal",
        "pdv",
        "pdrb",
    ),
    "last_price": ("last_price", "pDrCotVal", "pdv", "pl"),
    "previous_close": (
        "previous_close",
        "pYesterday",
        "priceYesterday",
        "py",
    ),
    "volume": ("volume", "qTotTran5J", "tvol", "qtj"),
    "value": ("value", "qTotCap", "tval", "qtc"),
    "trades": ("trades", "zTotTran", "tno", "ztt"),
}


def parse_market_date(value: Any) -> date | None:
    """Parse the Gregorian date formats used by TSETMC and SMART archives."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip().replace("-", "").replace("/", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value in (None, "", "-", ".", "NA", "N/A"):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result


def _first(row: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            # TSETMC often returns zero in a verbose field and a populated
            # compact alias.  Prefer the latter when it is available.
            if _number(value) == 0:
                continue
            return value
    # Preserve a genuine zero if every alias was zero.
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _row_date(row: dict[str, Any]) -> date | None:
    for key in DATE_KEYS:
        parsed = parse_market_date(row.get(key))
        if parsed:
            return parsed
    return None


def safe_symbol(value: str) -> str:
    """Make a symbol safe as one filesystem path component."""

    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip())
    return cleaned.rstrip(" .") or "UNKNOWN"


def normalize_daily_row(
    row: dict[str, Any],
    *,
    symbol: str = "",
    ins_code: str = "",
    source: str = "TSETMC",
) -> dict[str, Any] | None:
    """Return one analysis-ready row or ``None`` when its date is invalid.

    Canonical fields are stable English names.  ``source_date`` is ISO-8601,
    while ``date`` retains the compact Gregorian form used by legacy SMART
    code.  No synthetic zero is introduced for a missing value.
    """

    parsed = _row_date(row)
    if parsed is None:
        return None
    output: dict[str, Any] = {
        "date": parsed.strftime("%Y%m%d"),
        "source_date": parsed.isoformat(),
        "symbol": str(_first(row, ALIASES["symbol"]) or symbol or ""),
        "ins_code": str(_first(row, ALIASES["ins_code"]) or ins_code or ""),
        "source": source,
    }
    for field, names in ALIASES.items():
        if field in {"symbol", "ins_code"}:
            continue
        value = _first(row, names)
        number = _number(value)
        # TSETMC's historical endpoint uses zero as a placeholder for
        # unavailable price geometry (especially in early/illiquid records).
        # Keep zero volume/value/trade counts as real observations, but expose
        # non-positive price fields as missing so they do not create false
        # OHLC violations such as ``close > high == 0``.
        if field in {
            "open",
            "high",
            "low",
            "last_price",
            "previous_close",
        } and number is not None and number <= 0:
            number = None
        output[field] = number if number is not None else None
    # A deterministic fingerprint lets a quality report identify exactly
    # which source row won a duplicate-date merge.
    output["source_row_hash"] = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return output


def _completeness(row: dict[str, Any]) -> int:
    return sum(row.get(key) is not None for key in ("open", "high", "low", "close", "volume", "value", "trades"))


def deduplicate_rows(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str = "",
    ins_code: str = "",
    source: str = "TSETMC",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize and deduplicate rows by market date.

    If a date occurs more than once, the row with the greatest number of
    populated canonical fields wins.  Ties are resolved by source-row hash,
    which makes the output independent of input ordering.
    """

    source_rows = list(rows)
    by_date: dict[date, dict[str, Any]] = {}
    invalid = 0
    duplicate_dates: set[str] = set()
    for raw in source_rows:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        normalized = normalize_daily_row(raw, symbol=symbol, ins_code=ins_code, source=source)
        if normalized is None:
            invalid += 1
            continue
        key = date.fromisoformat(normalized["source_date"])
        previous = by_date.get(key)
        if previous is not None:
            duplicate_dates.add(normalized["source_date"])
            candidate_key = (_completeness(normalized), normalized["source_row_hash"])
            previous_key = (_completeness(previous), previous["source_row_hash"])
            if candidate_key > previous_key:
                by_date[key] = normalized
        else:
            by_date[key] = normalized
    ordered = [by_date[key] for key in sorted(by_date)]
    return ordered, {
        "input_rows": len(source_rows),
        "valid_rows": len(ordered),
        "invalid_rows": invalid,
        "duplicate_dates": len(duplicate_dates),
        "duplicate_date_values": sorted(duplicate_dates),
    }


def validate_canonical_rows(
    rows: Iterable[dict[str, Any]],
    *,
    strict_ohlc: bool = False,
) -> dict[str, Any]:
    """Validate canonical rows and return a serializable quality report.

    TSETMC's closing-price endpoint can expose a closing value whose
    adjustment basis differs from the raw intraday ``high``/``low`` fields
    around corporate actions.  Such a relationship is retained as a warning
    by default instead of being misclassified as corrupt data.  Set
    ``strict_ohlc=True`` when a downstream consumer requires textbook
    unadjusted OHLC geometry.
    """

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    valid_dates: list[date] = []
    for row in rows:
        market_date = parse_market_date(row.get("source_date") or row.get("date"))
        date_text = market_date.isoformat() if market_date else None
        if market_date is None:
            errors.append({"code": "INVALID_DATE", "field": "date"})
            continue
        if date_text in seen:
            errors.append({"code": "DUPLICATE_DATE", "date": date_text})
        seen.add(date_text)
        valid_dates.append(market_date)
        close = _number(row.get("close"))
        if close is None or close <= 0:
            errors.append({"code": "INVALID_CLOSE", "date": date_text, "value": close})
        numeric_fields = ("open", "high", "low", "volume", "value", "trades")
        for field in numeric_fields:
            value = _number(row.get(field))
            if value is not None and value < 0:
                errors.append(
                    {
                        "code": "NEGATIVE_VALUE",
                        "date": date_text,
                        "field": field,
                        "value": value,
                    }
                )
        high, low = _number(row.get("high")), _number(row.get("low"))
        if high is not None and low is not None and low > high:
            errors.append(
                {"code": "OHLC_RANGE", "date": date_text, "low": low, "high": high}
            )
        for field in ("open", "close", "last_price"):
            value = _number(row.get(field))
            if value is not None and high is not None and value > high:
                issue = {
                    "code": "PRICE_ABOVE_HIGH",
                    "date": date_text,
                    "field": field,
                    "severity": "ERROR" if strict_ohlc else "WARNING",
                    "reason": "adjusted_close_or_source_scale_mismatch",
                }
                (errors if strict_ohlc else warnings).append(issue)
            if value is not None and low is not None and value < low:
                issue = {
                    "code": "PRICE_BELOW_LOW",
                    "date": date_text,
                    "field": field,
                    "severity": "ERROR" if strict_ohlc else "WARNING",
                    "reason": "adjusted_close_or_source_scale_mismatch",
                }
                (errors if strict_ohlc else warnings).append(issue)
    ordered_dates = sorted(set(valid_dates))
    issues = errors + warnings
    return {
        "status": (
            "FAIL"
            if errors
            else "PASS_WITH_WARNINGS"
            if warnings
            else "PASS"
        ),
        "rows": len(ordered_dates),
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors[:200],
        "warnings": warnings[:200],
        "issues": issues[:200],
        "strict_ohlc": strict_ohlc,
        "first_date": ordered_dates[0].isoformat() if ordered_dates else None,
        "last_date": ordered_dates[-1].isoformat() if ordered_dates else None,
    }


def archive_monthly(
    symbol: str,
    rows: Iterable[dict[str, Any]],
    *,
    root: str | Path = "runtime/market_processed/canonical",
    ins_code: str = "",
    source: str = "TSETMC",
    metadata: dict[str, Any] | None = None,
    dry_run: bool = False,
    strict_ohlc: bool = False,
) -> dict[str, Any]:
    """Write deterministic monthly canonical archives and a quality report."""

    raw_rows = list(rows)
    normalized, dedup_report = deduplicate_rows(
        raw_rows, symbol=symbol, ins_code=ins_code, source=source
    )
    quality = validate_canonical_rows(normalized, strict_ohlc=strict_ohlc)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        grouped[row["source_date"][:7]].append(row)

    root_path = Path(root)
    archive_paths: list[str] = []
    generated_at = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        for month, month_rows in sorted(grouped.items()):
            target = root_path / safe_symbol(symbol) / f"{month.replace('-', '')}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": "2.2",
                "layer": "canonical",
                "source": source,
                "symbol": symbol,
                "ins_code": str(ins_code),
                "month": month,
                "generated_at": generated_at,
                "record_count": len(month_rows),
                "records": month_rows,
                # ``daily_history`` keeps old SMART readers compatible.
                "daily_history": month_rows,
                "metadata": metadata or {},
            }
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            archive_paths.append(os.fspath(target))
    report = {
        "schema_version": "1.0",
        "layer": "canonical",
        "symbol": symbol,
        "ins_code": str(ins_code),
        "source": source,
        "generated_at": generated_at,
        "dry_run": dry_run,
        "strict_ohlc": strict_ohlc,
        "deduplication": dedup_report,
        "quality": quality,
        "months": len(grouped),
        "archive_paths": archive_paths,
    }
    if not dry_run:
        quality_path = root_path / safe_symbol(symbol) / "quality_report.json"
        quality_path.parent.mkdir(parents=True, exist_ok=True)
        quality_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report["quality_report_path"] = os.fspath(quality_path)
    return report


def audit_archive_root(root: str | Path) -> dict[str, Any]:
    """Read-only audit of a derived archive root."""

    root_path = Path(root)
    files = sorted(root_path.rglob("*.json")) if root_path.exists() else []
    valid_files = 0
    invalid_files: list[str] = []
    symbols: dict[str, dict[str, Any]] = {}
    content_hashes: dict[str, list[str]] = defaultdict(list)
    for path in files:
        if path.name in {"quality_report.json", "metadata.json"}:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            invalid_files.append(os.fspath(path))
            continue
        valid_files += 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        content_hashes[digest].append(os.fspath(path))
        symbol = str(payload.get("symbol") or path.parent.name)
        rows = payload.get("records") or payload.get("daily_history") or []
        quality = validate_canonical_rows(
            row for row in rows if isinstance(row, dict)
        )
        entry = symbols.setdefault(symbol, {"files": 0, "rows": 0, "issues": 0})
        entry["files"] += 1
        entry["rows"] += quality["rows"]
        entry["issues"] += quality["issue_count"]
    duplicate_files = [paths for paths in content_hashes.values() if len(paths) > 1]
    return {
        "root": os.fspath(root_path),
        "files": len(files),
        "valid_files": valid_files,
        "invalid_files": invalid_files,
        "exact_duplicate_groups": duplicate_files,
        "exact_duplicate_file_count": sum(len(group) - 1 for group in duplicate_files),
        "symbols": symbols,
        "status": "PASS" if not invalid_files and not any(item["issues"] for item in symbols.values()) else "FAIL",
    }


def remove_exact_duplicate_derived_files(
    root: str | Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Optionally remove byte-identical files from a derived root.

    This helper never touches ``runtime/market_raw``.  Without ``apply=True``
    it is a dry-run and only reports candidates.
    """

    audit = audit_archive_root(root)
    removed: list[str] = []
    candidates: list[str] = []
    root_resolved = Path(root).resolve()
    for group in audit["exact_duplicate_groups"]:
        # Keep the lexicographically first path as the canonical copy.
        for candidate in sorted(group)[1:]:
            candidates.append(candidate)
            if apply:
                try:
                    candidate_path = Path(candidate).resolve()
                    if root_resolved not in candidate_path.parents:
                        continue
                    candidate_path.unlink()
                    removed.append(candidate)
                except OSError:
                    continue
    return {
        "root": os.fspath(Path(root)),
        "apply": apply,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "removed": removed,
        "status": "APPLIED" if apply else "DRY_RUN",
    }


__all__ = [
    "ALIASES",
    "archive_monthly",
    "audit_archive_root",
    "deduplicate_rows",
    "normalize_daily_row",
    "parse_market_date",
    "remove_exact_duplicate_derived_files",
    "safe_symbol",
    "validate_canonical_rows",
]
