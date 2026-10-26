"""Conservative Codal document parsing, independent of HTTP and synchronization."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

from .financial_history import METRICS, normalize, number, period_date, source_url


ALIASES = {
    "درآمدهای عملیاتی": "revenue", "بهای تمام شده درآمدهای عملیاتی": "cost_of_revenue",
    "بهای تمام شده کالای فروش رفته": "cost_of_revenue",
    "سود (زیان) ناخالص": "gross_profit", "سود (زیان) عملیاتی": "operating_profit",
    "سود (زیان) خالص": "net_profit", "سود (زیان) قبل از مالیات": "pretax_profit",
    "جمع داراییها": "assets", "جمع بدهیها": "liabilities",
    "جمع حقوق مالکانه": "equity", "حقوق مالکانه": "equity",
    "جمع حقوق صاحبان سهام": "equity", "جمع دارایی های جاری": "current_assets",
    "جمع دارایی های غیرجاری": "noncurrent_assets", "جمع بدهی های جاری": "current_liabilities",
    "جمع بدهی های غیرجاری": "noncurrent_liabilities",
    "جریان خالص ورود (خروج) نقد حاصل از فعالیت های عملیاتی": "operating_cash_flow",
    "خالص جریان های نقدی حاصل از فعالیت های عملیاتی": "operating_cash_flow",
    "خالص جریان های نقدی حاصل از فعالیت های سرمایه گذاری": "investing_cash_flow",
    "خالص جریان های نقدی حاصل از فعالیت های تامین مالی": "financing_cash_flow",
    "سود (زیان) خالص هر سهم": "eps",
}
ALIASES.update({normalize(v): k for k, v in METRICS.items()})
ALIASES.update({
    "سود(زیان) ناخالص": "gross_profit", "سود(زیان) عملیاتی": "operating_profit",
    "سود(زیان) خالص": "net_profit", "سود (زیان) خالص هر سهم– ریال": "eps",
    "سرمایه - میلیون ریال": "capital",
    "سود (زیان) خالص هر سهم – ریال": "eps",
    "هزینه های فروش، اداری و عمومی": "selling_expenses",
    "جریان خالص ورود (خروج) نقد حاصل از فعالیت های سرمایه گذاری": "investing_cash_flow",
    "جریان خالص ورود (خروج) نقد حاصل از فعالیت های تامین مالی": "financing_cash_flow",
    "خالص افزایش (کاهش) در موجودی نقد": "cash_change",
})


def metric_label(value: object) -> str:
    return normalize(str(value).replace("ى", "ی").replace("\u200f", "").replace("\u200e", "").replace("\u00ad", ""))


ALIASES = {metric_label(k): v for k, v in ALIASES.items()}
PARSER_VERSION = "CODAL-PARSER-4"


class CodalChallengeError(ValueError):
    """An HTTP 200 verification page is not a financial document."""


def is_verification_page(raw: str) -> bool:
    return bool(re.search(r'id=["\']captcha(?:Code|Image)["\']', raw, re.I))


def statement_links(raw, url, consolidated=True):
    """Use sheet IDs actually advertised in the report, not guessed IDs."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    select = re.search(r'<select[^>]+id=["\'](?:ctl00_)?ddlTable["\'][^>]*>(.*?)</select>', raw, re.S | re.I)
    if not select:
        return []
    links = []
    for match in re.finditer(r'<option\b([^>]*)>([^<]*)', select[1]):
        value = re.search(r'value=["\'](\d+)["\']', match[1])
        label = normalize(match[2])
        if not value or ("تلفیقی" in label) != consolidated:
            continue
        if not any(label == name + (" تلفیقی" if consolidated else "") for name in
                   ("صورت سود و زیان", "صورت وضعیت مالی", "صورت جریان های نقدی",
                    "ترازنامه", "جریان وجوه نقد", "صورت جریان وجوه نقد")):
            continue
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sheetId"]
        query.append(("sheetId", value[1]))
        links.append((label, urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))))
    return links


def issuer_report(letter, symbol):
    """Parent symbol search also returns subsidiary disclosures; fail closed."""
    if normalize(letter.get("Symbol", "")) != normalize(symbol):
        return False
    title = normalize(letter.get("Title", ""))
    companies = re.findall(r"\(\s*شرکت\s+([^)]*)\)", title)
    issuer = normalize(letter.get("CompanyName", "")).removeprefix("شرکت ")
    return all(normalize(company).removeprefix("شرکت ") == issuer for company in companies)


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.rows, self.row = [], None, None
        self.cell, self.links = None, []
        self.span = 1

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "table":
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []
            self.span = min(100, int(attrs.get("colspan", "1")))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.extend([normalize(" ".join(self.cell))] + [""] * (self.span - 1))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.tables.append(self.rows)
            self.rows = None


def embedded_tables(raw):
    """Decode JSON cell grids, without executing any remote JavaScript."""
    tables = []

    def visit(obj):
        if isinstance(obj, dict):
            cells = obj.get("cells")
            if isinstance(cells, list):
                grid = {}
                for cell in cells:
                    if not isinstance(cell, dict):
                        continue
                    address = re.fullmatch(r"([A-Z]{1,3})([1-9]\d*)", str(cell.get("address", "")))
                    if not address:
                        continue
                    col = 0
                    for char in address[1]:
                        col = col * 26 + ord(char) - 64
                    row = int(address[2])
                    if col > 100 or row > 10000:
                        continue
                    grid.setdefault(row, {})[col - 1] = normalize(cell.get("value", ""))
                if grid:
                    width = max(max(r) for r in grid.values()) + 1
                    tables.append([[grid[r].get(c, "") for c in range(width)] for r in sorted(grid)])
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(obj, list):
            for value in obj:
                visit(value)

    decoder = json.JSONDecoder()
    for match in re.finditer(r"(?:var\s+)?(?:datasource|dataSource|sheets)\s*=\s*", raw):
        try:
            obj, _ = decoder.raw_decode(raw[match.end():])
            visit(obj)
        except ValueError:
            continue
    return tables


def fiscal_columns(table, period):
    """Resolve one explicitly dated column per advertised description block.

    Old balance sheets place assets and liabilities side by side. Two date
    columns in the same block remain ambiguous and are never selected.
    """
    dates, descriptions = set(), {0}
    for row in table:
        if any(metric_label(cell).rstrip(":") in ALIASES for cell in row):
            break
        for index, cell in enumerate(row):
            if metric_label(cell) in {"شرح", "شرح حساب", "عنوان"}:
                descriptions.add(index)
            if re.findall(r"1[34]\d{2}/\d{2}/\d{2}", cell) == [period]:
                dates.add(index)
    starts = sorted(descriptions)
    groups = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else max((len(row) for row in table), default=0)
        selected = [column for column in dates if start < column < end]
        if len(selected) == 1:
            groups.append((start, selected[0], end))
    return groups


def parse_document(letter, raw, symbol, url):
    if raw.lstrip().startswith('{"codal_bundle":'):
        bundle = json.loads(raw)
        parts = [parse_document(bundle["letter"], item["raw"], symbol, item["url"])
                 for item in bundle["sheets"]]
        if not parts:
            raise ValueError("Empty statement bundle")
        result = dict(parts[0], source_url=url, metrics={})
        for index, part in enumerate(parts):
            for key in ("period", "months", "basis", "document_id", "audited"):
                if part[key] != result[key]:
                    raise ValueError("Incompatible statement sheets")
            for metric, cell in part["metrics"].items():
                old = result["metrics"].get(metric)
                if old and (old["value"], old["unit"]) != (cell["value"], cell["unit"]):
                    raise ValueError(f"Conflicting sheets: {metric}")
                result["metrics"][metric] = dict(cell, locator=f"sheet:{index}/" + cell["locator"],
                                                  source_url=part["source_url"])
        return result
    if not issuer_report(letter, symbol):
        raise ValueError("Codal symbol mismatch")
    title = normalize(letter.get("Title", ""))
    end = re.search(r"منتهی به\s*(1[34]\d{2}/\d{2}/\d{2})", title)
    length = re.search(r"(?:دوره\s*)?(3|6|9|12)\s*ماهه", title)
    if not length:
        # Actual annual announcement titles may omit the number of months.
        # Read the report's explicit period label rather than assume twelve.
        label = re.search(r'id=["\']ctl00_lblPeriod["\'][^>]*>(.*?)</span>', raw, re.S)
        if label:
            length = re.search(r"(3|6|9|12)\s*ماهه", normalize(re.sub(r"<[^>]+>", "", label[1])))
    if not end or not length:
        raise ValueError("Missing explicit fiscal end/period length")
    period = period_date(end[1])
    months = int(length[1])
    if "حسابرسی نشده" in title:
        audited = False
    elif "حسابرسی شده" in title:
        audited = True
    else:
        raise ValueError("Missing audit status")
    parser = Tables()
    parser.feed(raw)
    note = re.search(r'<p[^>]+id=["\']ctl00_pPriceNote["\'][^>]*>(.*?)</p>', raw, re.S)
    normalized_raw = normalize(re.sub(r"<[^>]+>", "", note[1])) if note else normalize(raw)
    # Mixed units require a richer parser. Do not silently scale financial values.
    units = [unit for label, unit in (("میلیون ریال", "million_IRR"), ("میلیارد ریال", "billion_IRR"))
             if label in normalized_raw]
    if len(units) != 1:
        raise ValueError("Missing or ambiguous statement unit")
    metrics = {}
    for ti, table in enumerate(parser.tables + embedded_tables(raw)):
        groups = fiscal_columns(table, period)
        for ri, row in enumerate(table):
            for start, ci, end in groups:
                for label in row[start:ci]:
                    metric = ALIASES.get(metric_label(label).rstrip(":"))
                    if not metric or ci >= len(row):
                        continue
                    if not any(str(v).strip() for v in row[ci:end]):
                        # Empty section headings are not reported metric rows.
                        continue
                    # Per-share/unit-rate/quantity fields require their own explicit unit.
                    unit = "IRR/share" if metric in {"eps", "dps"} else units[0]
                    if metric in {"shares", "production", "sales_quantity", "sales_rate"}:
                        continue
                    item = {"value": number(row[ci]), "unit": unit,
                            "locator": f"table:{ti}/row:{ri}/column:{ci}"}
                    if metric in metrics and metrics[metric]["value"] != item["value"]:
                        raise ValueError(f"Ambiguous metric: {metric}")
                    metrics[metric] = item
    if not metrics:
        raise ValueError("Unsupported Codal layout or no unambiguous fiscal column")
    # A consolidated announcement can contain both separate and group sheets.
    selected = re.search(r'<option\b(?=[^>]*selected)[^>]*>([^<]*)', raw)
    basis = "consolidated" if "تلفیقی" in title else "standalone"
    selected_label = normalize(selected[1]) if selected else ""
    if selected_label and any(term in selected_label for term in
                              ("صورت", "ترازنامه", "جریان وجوه نقد")) and "نظر حسابرس" not in selected_label:
        basis = "consolidated" if "تلفیقی" in selected_label else "standalone"
    year_end = re.search(r'id=["\']ctl00_lblYearEndToDate["\'][^>]*>(.*?)</span>', raw, re.S)
    fiscal_year_end = None
    if year_end:
        found = re.search(r"1[34]\d{2}/\d{2}/\d{2}", normalize(re.sub(r"<[^>]*>", "", year_end[1])))
        fiscal_year_end = found[0] if found else None
    match = re.search(r"(?:var\s+)?datasource\s*=\s*", raw)
    if match:
        metadata, _ = json.JSONDecoder().raw_decode(raw[match.end():])
        if str(metadata.get("tracingNo")) != str(letter["TracingNo"]):
            raise ValueError("Report body ID differs from discovery ID")
        if metadata.get("periodEndToDate") != period or metadata.get("period") != months:
            raise ValueError("Report body period differs from discovery period")
        if metadata.get("yearEndToDate"):
            fiscal_year_end = period_date(metadata["yearEndToDate"])
    for cell in metrics.values():
        cell.update(source_type="DIRECT", raw_value=cell["value"], raw_unit=cell["unit"])
        factor = {"million_IRR": 1000000, "billion_IRR": 1000000000}.get(cell["unit"], 1)
        cell.update(normalized_value=cell["value"] * factor if cell["value"] is not None else None,
                    normalized_unit="IRR" if factor != 1 else cell["unit"], normalization_factor=factor)
    return {"symbol": normalize(symbol), "source": "KODAL", "source_url": url,
            "parser_version": PARSER_VERSION,
            "source_title": title,
            "company": letter.get("CompanyName"), "fiscal_year_end": fiscal_year_end,
            "source_date": normalize(letter["PublishDateTime"]),
            "document_id": str(letter["TracingNo"]), "period": period,
            "months": months, "report_type": "annual" if months == 12 else "interim",
            "basis": basis,
            "audited": audited, "restated": "اصلاح" in title or "تجدید ارائه" in title,
            "metrics": metrics}
