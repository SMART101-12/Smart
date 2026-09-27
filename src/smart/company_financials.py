"""Local company datasets and explicit, traceable period calculations.

No forecasts and no price predictions. Missing operands never become zero.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .financial_history import METRICS, normalize, now


FLOW_METRICS = ("revenue", "gross_profit", "operating_profit", "net_profit",
                "cost_of_revenue", "selling_expenses", "finance_cost", "tax",
                "operating_cash_flow", "investing_cash_flow", "financing_cash_flow")


def reference(report, metric):
    cell = report["metrics"].get(metric, {})
    return {"report_id": report["document_id"], "content_hash": report["digest"],
            "period": report["period"], "published_at": report["source_date"],
            "source_url": cell.get("source_url", report["source_url"]),
            "locator": cell.get("locator"), "metric": metric}


def fact(value, unit, method, sources, reason=None):
    if value is not None and not math.isfinite(value):
        value, reason = None, "Non-finite calculation"
    return {"value": value, "unit": unit, "source": "KODAL",
            "source_type": "DIRECT" if method == "DIRECT" and value is not None else
                           "CALCULATED" if value is not None else None,
            "calculation_method": method, "source_records": sources, "missing_reason": reason}


def scalar(report, metric):
    item = report["metrics"].get(metric, {})
    return item.get("normalized_value", item.get("value")), item.get("normalized_unit", item.get("unit"))


def quarterly_financials(reports):
    """Derive actual fiscal quarters, requiring explicit common fiscal year end.

    Annual year end can identify itself; interim periods need source metadata.
    No assumption that every issuer closes in Esfand. EPS is not additive when
    the weighted-average share denominator changes, so it is direct in Q1 only.
    """
    grouped = defaultdict(dict)
    rejected = []
    for report in reports:
        if report["report_type"] not in {"annual", "interim"}:
            continue
        year_end = report.get("fiscal_year_end") or (report["period"] if report["months"] == 12 else None)
        if not year_end:
            rejected.append({"report_id": report["document_id"], "reason": "Missing fiscal year end"})
            continue
        end_y, end_m, _ = map(int, year_end.split("/"))
        period_y, period_m, _ = map(int, report["period"].split("/"))
        months = report["months"]
        if (end_y * 12 + end_m) - (period_y * 12 + period_m) != 12 - months:
            rejected.append({"report_id": report["document_id"], "reason": "Incompatible fiscal boundaries"})
            continue
        grouped[(year_end, report["basis"])][months] = report
    rows = []
    for (year_end, basis), periods in sorted(grouped.items()):
        for months in (3, 6, 9, 12):
            current, prior = periods.get(months), periods.get(months - 3)
            cells = {}
            for metric in (*FLOW_METRICS, "eps"):
                value, unit = scalar(current, metric) if current else (None, None)
                refs = [reference(current, metric)] if current and value is not None else []
                method = "DIRECT" if months == 3 else "CUMULATIVE_PERIOD_DIFFERENCE"
                reason = None
                if months != 3:
                    earlier, prior_unit = scalar(prior, metric) if prior else (None, None)
                    if metric == "eps":
                        value, reason = None, "EPS denominators are not proven comparable; cumulative EPS is not additive"
                    elif value is None or earlier is None or unit != prior_unit:
                        value, reason = None, "Missing or incompatible cumulative operand"
                    elif current["restated"] != prior["restated"]:
                        value, reason = None, "Restatement bases differ"
                    else:
                        value -= earlier
                        refs.append(reference(prior, metric))
                elif value is None:
                    reason = "No direct three-month disclosure"
                cells[metric] = fact(value, unit, method, refs, reason)
            rows.append({"fiscal_year_end": year_end, "quarter": months // 3, "basis": basis,
                         "period": current["period"] if current else None, "metrics": cells})
    return rows, rejected


def monthly_quarters(monthly):
    """Calendar quarters require all three distinct monthly observations."""
    groups = defaultdict(dict)
    for row in monthly:
        year, month = map(int, row["period"].split("/")[:2])
        groups[(year, (month - 1) // 3 + 1, row.get("basis", "standalone"))][month] = row
    output = []
    for (year, quarter, basis), months in sorted(groups.items()):
        expected = set(range((quarter - 1) * 3 + 1, quarter * 3 + 1))
        cells = [r["sales_value"] for r in months.values()]
        complete = set(months) == expected and all(c["value"] is not None for c in cells)
        units = {c["unit"] for c in cells}
        value = sum(c["value"] for c in cells) if complete and len(units) == 1 else None
        refs = [ref for c in cells for ref in c["source_records"]]
        output.append({"year": year, "quarter": quarter, "basis": basis,
                       "period_type": "JALALI_CALENDAR_QUARTER", "months_available": len(months),
                       "sales": fact(value, next(iter(units)) if len(units) == 1 else None,
                                     "SUM(monthly_values)", refs,
                                     None if value is not None else "Three complete compatible months required")})
    return output


def quarterly_trends(rows):
    output = []
    lookup = {}
    for row in rows:
        year = int(row["fiscal_year_end"][:4])
        key = (row["basis"], row["fiscal_year_end"][5:], year, row["quarter"])
        lookup[key] = row
    for row in rows:
        year = int(row["fiscal_year_end"][:4])
        q = row["quarter"]
        base = (row["basis"], row["fiscal_year_end"][5:])
        result = {"fiscal_year_end": row["fiscal_year_end"], "quarter": q, "basis": row["basis"], "metrics": {}}
        for metric in ("revenue", "net_profit", "eps"):
            cell = row["metrics"][metric]
            for label, prev_year, prev_q in (("yoy", year - 1, q), ("qoq", year if q > 1 else year - 1, q - 1 if q > 1 else 4)):
                prior = lookup.get((*base, prev_year, prev_q), {}).get("metrics", {}).get(metric)
                valid = prior and cell["value"] is not None and prior["value"] is not None and prior["value"] > 0 and cell["unit"] == prior["unit"]
                value = (cell["value"] / prior["value"] - 1) if valid else None
                result["metrics"][metric + "_" + label] = fact(value, "ratio", "current / previous - 1",
                    cell["source_records"] + (prior["source_records"] if prior else []),
                    None if valid else "Positive comparable baseline required")
        for name, numerator in (("gross_margin", "gross_profit"), ("operating_margin", "operating_profit"), ("net_margin", "net_profit")):
            a, b = row["metrics"][numerator], row["metrics"]["revenue"]
            valid = a["value"] is not None and b["value"] is not None and b["value"] > 0 and a["unit"] == b["unit"]
            result["metrics"][name] = fact(a["value"] / b["value"] if valid else None, "ratio", numerator + "/revenue",
                                          a["source_records"] + b["source_records"])
        output.append(result)
    return output


def seasonality(quarters):
    years = defaultdict(dict)
    for row in quarters:
        if row["sales"]["value"] is not None:
            years[(row["basis"], row["year"], row["sales"]["unit"])][row["quarter"]] = row
    # Match complete years: never compare Q4 from one sample to Q1 from another.
    complete = {key: value for key, value in years.items() if set(value) == {1, 2, 3, 4}}
    output = []
    for basis, unit in sorted({(k[0], k[2]) for k in complete}):
        sample = [v for k, v in complete.items() if k[0] == basis and k[2] == unit]
        averages = {str(q): fact(mean(y[q]["sales"]["value"] for y in sample) if len(sample) >= 3 else None,
            unit, "MEAN(observed same-quarter sales in matched complete years)",
            [ref for y in sample for ref in y[q]["sales"]["source_records"]]) for q in (1, 2, 3, 4)}
        output.append({"basis": basis, "matched_years": len(sample), "quarter_averages": averages,
                       "description": "میانگین فصلی از سال‌های کامل؛ این مقایسه پیش‌بینی نیست." if len(sample) >= 3 else "سابقه کامل برای توصیف فصل‌محوری کافی نیست."})
    return output


def company_dataset(repo, symbol):
    reports = [r for basis in ("standalone", "consolidated") for r in repo.reports(symbol, basis)]
    quarterly, issues = quarterly_financials(reports)
    monthly = repo.monthly_sales(symbol)
    sales = monthly_quarters(monthly)
    versions = [r for basis in ("standalone", "consolidated") for r in repo.reports(symbol, basis, selected=False)]
    report_ids = {r["document_id"] for r in versions} | {r["report_id"] for r in monthly}
    data = {"symbol": normalize(symbol), "source": "KODAL", "generated_at": now(),
            "financial_data": reports, "quarterly_financials": quarterly, "quarterly_sales": sales,
            "monthly_sales": monthly, "product_sales": repo.product_sales(symbol),
            "trend_metrics": quarterly_trends(quarterly), "seasonality": seasonality(sales),
            "issues": issues, "data_quality": {
                "financial_years_available": len({r["period"][:4] for r in reports if r["months"] == 12}),
                "quarters_with_revenue": sum(r["metrics"]["revenue"]["value"] is not None for r in quarterly),
                "quarters_in_observed_fiscal_years": len(quarterly),
                "monthly_sales_periods": len(monthly), "report_count": len(report_ids),
                "last_report_date": max([r["source_date"] for r in reports] + [r["publish_date"] for r in monthly], default=None),
                "missing_metrics": {m: sum(r["metrics"].get(m, {}).get("value") is None for r in reports) for m in METRICS},
                "source_status": repo.state(symbol, "KODAL").get("status", "NOT_SYNCED"),
                "last_sync_date": repo.state(symbol, "KODAL").get("last_sync_date")}}
    return data


def export_company(repo, symbol, root):
    data = company_dataset(repo, symbol)
    # Stable ASCII identifier, never a guessed exchange ticker or unsafe filename.
    safe_id = hashlib.sha256(normalize(symbol).encode()).hexdigest()[:16]
    target = Path(root).resolve() / safe_id
    target.mkdir(parents=True, exist_ok=True)
    for key in ("financial_data", "quarterly_sales", "monthly_sales", "product_sales", "trend_metrics", "seasonality"):
        (target / f"{key}.json").write_text(json.dumps(data[key], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (target / "quarterly_profit.json").write_text(json.dumps(data["quarterly_financials"], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (target / "metadata.json").write_text(json.dumps({k: data[k] for k in ("symbol", "source", "generated_at", "data_quality", "issues")}, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_root = target / "raw_reports"
    raw_root.mkdir(exist_ok=True)
    with repo._connect() as con:
        for digest, payload in con.execute("SELECT digest,payload FROM codal_assets WHERE symbol=?", (normalize(symbol),)):
            (raw_root / f"{digest}.raw").write_bytes(payload)
        for digest, raw in con.execute("SELECT digest,raw FROM financial_documents WHERE symbol=?", (normalize(symbol),)):
            (raw_root / f"{digest}.txt").write_text(raw, encoding="utf-8")
    return str(target)
