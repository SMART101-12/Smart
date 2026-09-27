"""Observed Codal evidence for investment funds, without equity scoring."""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re

import httpx

from .financial_history import HistoricalDataRepository, normalize, number, source_url
from .codal import Tables, embedded_tables, CodalHistoricalProvider


def is_fund_instrument(instrument: dict[str, Any]) -> bool:
    name = str(instrument.get("lVal30") or instrument.get("company_name") or "")
    return "صندوق" in name


def fund_asset_link(raw: str, base_url: str) -> str | None:
    if not source_url(base_url):
        return None
    select = re.search(r'<select[^>]+id=["\']ddlTable["\'][^>]*>(.*?)</select>', raw, re.S)
    if not select:
        return None
    options = []
    for sheet_id, label in re.findall(r'<option[^>]*value=["\'](\d+)["\'][^>]*>([^<]*)', select[1]):
        if normalize(label).replace("‌", " ") == "صورت خالص دارایی ها":
            options.append(sheet_id)
    if len(options) != 1:
        return None
    parts = urlsplit(base_url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "sheetId"]
    query.append(("sheetId", options[0]))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def parse_fund_asset_sheet(raw: str, period: str, url: str, document_id: str) -> dict[str, Any]:
    """Take only uniquely labeled, explicitly dated values from the fund grid."""
    parser = Tables()
    parser.feed(raw)
    facts = {}
    labels = {"جمع دارایی ها": "total_assets", "جمع بدهی ها": "total_liabilities"}
    for table_index, table in enumerate(parser.tables + embedded_tables(raw)):
        columns = {column for row in table[:5] for column, value in enumerate(row)
                   if re.findall(r"1[34]\d{2}/\d{2}/\d{2}", value) == [period]}
        if len(columns) != 1:
            continue
        column = next(iter(columns))
        for row_index, row in enumerate(table):
            if column >= len(row):
                continue
            label = normalize(row[0]).rstrip(":") if row else ""
            metric = labels.get(label)
            if "خالص ارزش" in label and "دارایی" in label:
                metric = "nav_per_unit" if "هر واحد" in label or "به ازای هر واحد" in label else "net_assets"
            elif "خالص دارایی" in label:
                metric = "nav_per_unit" if "هر واحد" in label or "به ازای هر واحد" in label else "net_assets"
            elif label.startswith("خالص ارزش هر واحد"):
                metric = "nav_per_unit"
            if not metric:
                continue
            value = number(row[column])
            if value is None:
                continue
            if metric in {"nav_per_unit", "net_assets", "total_assets"} and value <= 0:
                # Codal fund templates may publish 0 for an unpopulated per-unit
                # field. Never turn that placeholder into a verified NAV.
                continue
            if metric in facts and facts[metric]["value"] != value:
                raise ValueError("Conflicting fund asset cells")
            unit = "IRR/unit" if metric == "nav_per_unit" and "ریال" in label else (
                "million_IRR" if "میلیون ریال" in normalize(raw) else None)
            if unit is None:
                continue
            facts[metric] = {"value": value, "unit": unit, "source": "KODAL",
                             "document_id": document_id, "source_url": url,
                             "locator": f"table:{table_index}/row:{row_index}/column:{column}"}
    return facts


def zero_nav_observation(raw: str, period: str, url: str, document_id: str) -> dict[str, Any] | None:
    parser = Tables()
    parser.feed(raw)
    for table_index, table in enumerate(parser.tables + embedded_tables(raw)):
        columns = {column for row in table[:5] for column, cell in enumerate(row)
                   if re.findall(r"1[34]\d{2}/\d{2}/\d{2}", cell) == [period]}
        if len(columns) != 1:
            continue
        column = next(iter(columns))
        for row_index, row in enumerate(table):
            if column >= len(row):
                continue
            label = normalize(row[0])
            if "هر واحد" in label and ("خالص دارایی" in label or "خالص ارزش" in label):
                if number(row[column]) == 0:
                    return {"reported_value": 0, "status": "UNUSABLE_ZERO",
                            "document_id": document_id, "source_url": url,
                            "locator": f"table:{table_index}/row:{row_index}/column:{column}"}
    return None


def fund_financial_evidence(repository: HistoricalDataRepository, symbol: str,
                            *, fetch_missing: bool = True, as_of=None) -> dict[str, Any]:
    from .data_quality_gate import source_date_cutoff
    candidates = repository.reports(symbol, selected=False) if as_of is not None else repository.reports(symbol)
    reports = [report for report in candidates
               if as_of is None or source_date_cutoff(report["source_date"], as_of=as_of)]
    chosen = {}
    for report in sorted(reports, key=lambda r: (r.get("audited", False), r["source_date"],
                                                 r.get("restated", False), r.get("retrieved_at", ""))):
        chosen[(report["period"], report["report_type"])] = report
    reports = [report for report in sorted(chosen.values(), key=lambda r: r["period"])
               if report["report_type"] == "annual" and report["months"] == 12]
    annual = []
    for report in reports[-5:]:
        cells = {}
        for name in ("net_profit", "assets", "liabilities", "finance_cost"):
            item = report["metrics"].get(name)
            if item and item.get("value") is not None:
                cells[name] = {"value": item["value"], "unit": item["unit"],
                               "source": "KODAL", "document_id": report["document_id"],
                               "source_url": item.get("source_url") or report["source_url"],
                               "locator": item["locator"],
                               "published_at": report["source_date"]}
        annual.append({"period": report["period"], "audited": report["audited"],
                       "document_id": report["document_id"], "metrics": cells})
    observed = sum(len(row["metrics"]) for row in annual)
    asset_cells = {}
    unusable_nav = None
    source_error = None
    if reports:
        latest = reports[-1]
        cached_base = repository.asset(symbol, latest["document_id"], latest["source_url"])
        if cached_base:
            raw_base = cached_base["payload"].decode("utf-8-sig")
            asset_url = fund_asset_link(raw_base, latest["source_url"])
            if asset_url:
                asset = repository.asset(symbol, latest["document_id"], asset_url)
                if not asset and fetch_missing:
                    try:
                        with httpx.Client(timeout=8, follow_redirects=False,
                                          headers={"User-Agent": "SMART/1.0"}) as client:
                            raw_sheet = CodalHistoricalProvider(client, repository).download(
                                symbol, latest["document_id"], asset_url)
                        asset_cells = parse_fund_asset_sheet(raw_sheet, latest["period"],
                                                              asset_url, latest["document_id"])
                        unusable_nav = zero_nav_observation(raw_sheet, latest["period"],
                                                             asset_url, latest["document_id"])
                    except (httpx.HTTPError, ValueError, UnicodeError) as exc:
                        source_error = str(exc)
                elif asset:
                    try:
                        raw_sheet = asset["payload"].decode("utf-8-sig")
                        asset_cells = parse_fund_asset_sheet(raw_sheet,
                                                              latest["period"], asset_url,
                                                              latest["document_id"])
                        unusable_nav = zero_nav_observation(raw_sheet, latest["period"],
                                                             asset_url, latest["document_id"])
                    except (ValueError, UnicodeError) as exc:
                        source_error = str(exc)
                if not asset_cells and not source_error:
                    source_error = "Net-assets cells unavailable or unrecognized"
            else:
                source_error = "Net-assets sheet not advertised in cached report"
        else:
            source_error = "Official report body not cached"
    return {
        "instrument_type": "FUND", "symbol": symbol,
        "status": "PARTIAL" if observed or asset_cells else "NOT_AVAILABLE",
        "source": "KODAL" if observed or asset_cells else None,
        "financial_score": None, "equity_score_applicable": False,
        "coverage": {"annual_reports": len(annual), "observed_cells": observed},
        "annual": annual,
        "net_asset_value_per_unit": asset_cells.get("nav_per_unit"),
        "unusable_nav_observation": unusable_nav,
        "asset_statement": asset_cells,
        "missing_data": (["verified_nav_per_unit"] if "nav_per_unit" not in asset_cells else [])
                        + (["fund_asset_statement"] if not asset_cells else []),
        "source_error": source_error,
        "explanation": "This is an investment fund; company revenue, EPS and debt scoring do not apply. Only observed fund cells are shown.",
        "sync": repository.state(symbol, "KODAL"),
    }
