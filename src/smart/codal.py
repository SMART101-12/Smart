"""Read-only Codal acquisition with conservative, evidence-preserving parsing.

Unsupported layouts are rejected, never approximated. Report columns require
an explicit fiscal end date; comparative columns cannot become current values.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from threading import Lock
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from .financial_history import METRICS, normalize, number, now, period_date, source_url


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
})


def metric_label(value):
    return normalize(value).replace("ى", "ی").replace("\u200f", "").replace("\u200e", "")


ALIASES = {metric_label(k): v for k, v in ALIASES.items()}


def statement_links(raw, url, consolidated=True):
    """Use sheet IDs actually advertised in the report, not guessed IDs."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    select = re.search(r'<select[^>]+id=["\']ddlTable["\'][^>]*>(.*?)</select>', raw, re.S)
    if not select:
        return []
    links = []
    for match in re.finditer(r'<option\b([^>]*)>([^<]*)', select[1]):
        value = re.search(r'value=["\'](\d+)["\']', match[1])
        label = normalize(match[2])
        if not value or ("تلفیقی" in label) != consolidated:
            continue
        if not any(label == name + (" تلفیقی" if consolidated else "") for name in
                   ("صورت سود و زیان", "صورت وضعیت مالی", "صورت جریان های نقدی")):
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
        columns = set()
        for ri, row in enumerate(table):
            # Only header cells select columns, never labels or data cells.
            if not any(metric_label(cell).rstrip(":") in ALIASES for cell in row):
                for ci, cell in enumerate(row):
                    dates = re.findall(r"1[34]\d{2}/\d{2}/\d{2}", cell)
                    if dates == [period]:
                        columns.add(ci)
            if len(columns) != 1:
                continue
            ci = next(iter(columns))
            for label in row[:ci]:
                metric = ALIASES.get(metric_label(label).rstrip(":"))
                if not metric or ci >= len(row):
                    continue
                if not any(str(v).strip() for v in row[ci:]):
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
    if selected and "صورت" in selected[1] and "نظر حسابرس" not in selected[1]:
        basis = "consolidated" if "تلفیقی" in selected[1] else "standalone"
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
            "source_title": title,
            "company": letter.get("CompanyName"), "fiscal_year_end": fiscal_year_end,
            "source_date": normalize(letter["PublishDateTime"]),
            "document_id": str(letter["TracingNo"]), "period": period,
            "months": months, "report_type": "annual" if months == 12 else "interim",
            "basis": basis,
            "audited": audited, "restated": "اصلاح" in title or "تجدید ارائه" in title,
            "metrics": metrics}


class CodalHistoricalProvider:
    search_url = "https://search.codal.ir/api/search/v2/q"

    def __init__(self, client=None, repository=None):
        self.client = client
        self.repository = repository

    def get(self, url, *, params=None):
        """Bounded retries; follow only official report redirects."""
        for attempt in range(3):
            try:
                for _ in range(4):
                    response = self.client.get(url, params=params)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        target = urljoin(str(response.url), response.headers.get("location", ""))
                        if not source_url(target):
                            raise ValueError("Untrusted report redirect")
                        url, params = target, None
                        continue
                    response.raise_for_status()
                    return response
                raise ValueError("Too many report redirects")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
            except httpx.HTTPStatusError as exc:
                if attempt == 2 or (exc.response.status_code < 500 and exc.response.status_code != 429):
                    raise

    def download(self, symbol, docid, url, refresh=False):
        cached = self.repository.asset(symbol, docid, url) if self.repository and not refresh else None
        if cached:
            return cached["payload"].decode("utf-8-sig", errors="strict")
        response = self.get(url)
        raw = response.content.decode("utf-8-sig", errors="strict")
        if self.repository:
            self.repository.save_asset(symbol, docid, url, response.content,
                                       response.headers.get("content-type", ""))
        return raw

    def download_statements(self, letter, symbol, url, refresh=False):
        raw = self.download(symbol, letter["TracingNo"], url, refresh)
        results = []
        for consolidated in (False, True):
            links = statement_links(raw, url, consolidated)
            if not links:
                continue
            sheets = []
            for label, link in links:
                sheet = self.download(symbol, letter["TracingNo"], link, refresh)
                # No sheet with an unsupported format is silently presented as complete.
                parse_document(letter, sheet, symbol, link)
                sheets.append({"url": link, "label": label, "raw": sheet})
            bundle = json.dumps({"codal_bundle": 1, "letter": letter, "sheets": sheets}, ensure_ascii=False)
            results.append((parse_document(letter, bundle, symbol, url), bundle))
        return results or [(parse_document(letter, raw, symbol, url), raw)]

    def fetch(self, symbol, known_ids, publication_cursor=None, years=5):
        """Discover announcements; only download unknown reports.

        The publication cursor (not fiscal year) discovers amendments to older
        periods. Initial discovery is bounded; incomplete pagination is explicit.
        """
        if self.client is None:
            with httpx.Client(timeout=20, follow_redirects=False,
                              headers={"User-Agent": "SMART/1.0"}) as client:
                return CodalHistoricalProvider(client, self.repository).fetch(symbol, known_ids, publication_cursor, years)
        output, rejected, periods = [], [], set()
        downloaded = set(known_ids)
        seen_pages = set()
        newest = publication_cursor
        for page in range(1, 101):
            params = {"Symbol": symbol, "Category": 1, "Length": 12,
                      "PageNumber": page, "IsNotAudited": True, "IsAudited": True}
            if publication_cursor:
                params["FromDate"] = publication_cursor[:10]
            try:
                response = self.get(self.search_url, params=params)
                data = response.json()
                letters = data.get("Letters") if isinstance(data, dict) else None
                if not isinstance(letters, list) or any(not isinstance(x, dict) for x in letters):
                    raise ValueError("Invalid Codal search response")
            except (httpx.HTTPError, ValueError) as exc:
                # Preserve already downloaded evidence when a later page fails.
                rejected.append({"page": page, "error": str(exc)})
                break
            if not letters:
                break
            fingerprint = tuple(str(letter.get("TracingNo", "")) for letter in letters)
            if fingerprint in seen_pages:
                rejected.append({"page": page, "error": "Repeated Codal page; discovery incomplete"})
                break
            seen_pages.add(fingerprint)
            for letter in letters:
                docid = str(letter.get("TracingNo", ""))
                title = normalize(letter.get("Title", ""))
                if not issuer_report(letter, symbol):
                    continue
                publication = normalize(letter.get("PublishDateTime", ""))
                if publication:
                    newest = max(newest or publication, publication)
                changed = self.repository.announcement_changed(symbol, letter) if self.repository else False
                if docid in downloaded and not changed:
                    continue
                if not ("12 ماهه" in title or "سال مالی" in title) or "صورت" not in title or "مالی" not in title:
                    continue
                url = urljoin("https://www.codal.ir/", letter.get("Url", ""))
                try:
                    if not docid or not source_url(url):
                        raise ValueError("Missing document identity or untrusted URL")
                    parsed = self.download_statements(letter, symbol, url, changed)
                    output.extend(parsed)
                    downloaded.add(docid)
                    for report, _ in parsed:
                        if report["basis"] == "standalone":
                            periods.add(report["period"])
                except (ValueError, KeyError, httpx.HTTPError) as exc:
                    rejected.append({"document_id": docid, "source_url": url, "error": str(exc)})
            # 'Page' may describe the current page. Only an explicit total is
            # a safe stopping condition; otherwise stop on an empty response.
            total_pages = data.get("TotalPages")
            if isinstance(total_pages, int) and total_pages > 0 and page >= total_pages:
                break
            if not publication_cursor and len(periods) >= years + 1:
                break
        else:
            rejected.append({"error": "Codal pagination limit reached; discovery incomplete"})
        return {"reports": output, "rejected": rejected, "cursor": newest}

    def sync_company(self, symbol, *, years=5, max_pages=100, force=False):
        """Checkpoint each report in SQLite; resume using cached raw assets.

        Category IDs were read from Codal's v1/categories response, not inferred
        from titles. Titles determine which data parser is appropriate.
        """
        from .financial_history import settings
        from .codal_operations import parse_monthly
        from .company_financials import company_dataset
        repo = self.repository
        if repo is None:
            raise ValueError("Company sync requires a repository")
        if years < 5 or max_pages < 1 or max_pages > 100:
            raise ValueError("At least five years; pages must be 1..100")
        if self.client is None:
            with httpx.Client(timeout=12, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 SMART"}) as client:
                return CodalHistoricalProvider(client, repo).sync_company(symbol, years=years, max_pages=max_pages, force=force)
        state = repo.state(symbol, "KODAL_COMPANY")
        if not force and repo.fresh(symbol, "KODAL_COMPANY", settings()["sync_ttl_seconds"]):
            return dict(state, reused_local=True)
        cursor = state.get("cursor") if state.get("status") == "SUCCESS" else None
        result = {"symbol": normalize(symbol), "source": "KODAL", "status": "SUCCESS",
                  "inserted": 0, "updated": 0, "skipped": 0, "discovered": 0,
                  "rejected": [], "pages": [], "cursor": cursor,
                  "last_sync_date": state.get("last_sync_date")}
        known = repo.known_documents(symbol) | {r["report_id"] for r in repo.monthly_sales(symbol, selected=False)}
        newest = cursor
        for category in (1, 3):
            seen, first_year = set(), None
            for page in range(1, max_pages + 1):
                params = {"Symbol": symbol, "Category": category, "PageNumber": page,
                          "IsAudited": True, "IsNotAudited": True, "Childs": False, "Mains": True}
                if cursor:
                    params["FromDate"] = cursor[:10]
                try:
                    response = self.get(self.search_url, params=params)
                    data = response.json()
                    letters = data.get("Letters") if isinstance(data, dict) else None
                    if not isinstance(letters, list) or any(not isinstance(x, dict) for x in letters):
                        raise ValueError("Invalid discovery response")
                except (httpx.HTTPError, ValueError) as exc:
                    result["rejected"].append({"category": category, "page": page, "error": str(exc)})
                    break
                result["pages"].append({"category": category, "page": page, "count": len(letters)})
                if not letters:
                    break
                fingerprint = tuple(str(x.get("TracingNo")) for x in letters)
                if fingerprint in seen:
                    result["rejected"].append({"category": category, "page": page, "error": "Repeated discovery page"})
                    break
                seen.add(fingerprint)
                page_years = []
                for letter in letters:
                    if not issuer_report(letter, symbol):
                        continue
                    title = normalize(letter.get("Title", ""))
                    financial = "صورت" in title and "مالی" in title
                    monthly = "فعالیت ماهانه" in title
                    if not financial and not monthly:
                        # Preserve discovery metadata for relevant supplemental
                        # disclosures without inventing numeric extraction rules.
                        if letter.get("TracingNo"):
                            repo.announcement_changed(symbol, letter)
                        continue
                    found = re.search(r"منتهی به\s*(1[34]\d{2})/", title)
                    if found:
                        page_years.append(int(found[1]))
                        first_year = max(first_year or int(found[1]), int(found[1]))
                    docid = str(letter.get("TracingNo", ""))
                    if not docid:
                        result["rejected"].append({"error": "Missing report ID"})
                        continue
                    result["discovered"] += 1
                    changed = repo.announcement_changed(symbol, letter)
                    publication = normalize(letter.get("PublishDateTime", ""))
                    if publication:
                        newest = max(newest or publication, publication)
                    if docid in known and not changed:
                        result["skipped"] += 1
                        continue
                    url = urljoin("https://www.codal.ir/", letter.get("Url", ""))
                    try:
                        if not source_url(url):
                            raise ValueError("Untrusted report URL")
                        if monthly:
                            raw = self.download(symbol, docid, url, changed)
                            parsed = parse_monthly(letter, raw, symbol, url)
                            result[repo.save_monthly(parsed, raw)] += 1
                        else:
                            for report, raw in self.download_statements(letter, symbol, url, changed):
                                result[repo.save_report(report, raw)] += 1
                        known.add(docid)
                    except (ValueError, TypeError, KeyError, httpx.HTTPError) as exc:
                        result["rejected"].append({"report_id": docid, "source_url": url, "error": str(exc)})
                # Keep the entire last fetched page, including older evidence.
                # Initial window covers five *completed* fiscal years plus current.
                if not cursor and page_years and first_year and max(page_years) < first_year - years:
                    break
                total = data.get("TotalPages")
                if type(total) is int and page >= total:
                    break
                # Official live v2 response uses Page for its page count (Total=423,
                # Page=22). Repeated-page detection still guards incompatible servers.
                total = data.get("Page")
                if type(total) is int and total > 1 and page >= total:
                    break
            else:
                result["rejected"].append({"category": category, "error": "Page budget reached; resume required"})
        result["status"] = "PARTIAL" if result["rejected"] else "SUCCESS"
        if result["status"] == "SUCCESS":
            result["cursor"], result["last_sync_date"] = newest, now()
        datasets = company_dataset(repo, symbol)
        for name in ("quarterly_financials", "quarterly_sales", "trend_metrics", "seasonality", "data_quality"):
            repo.save_calculated_dataset(symbol, name, datasets[name])
        result["data_quality"] = datasets["data_quality"]
        return repo.record_sync(symbol, "KODAL_COMPANY", result)


class HistoricalDataSyncManager:
    def __init__(self, repository, provider=None):
        self.repository = repository
        self.provider = provider or CodalHistoricalProvider(repository=repository)

    def sync_financial(self, symbol, force=False):
        with _sync_lock(str(self.repository.path.resolve()), normalize(symbol)):
            return self._sync_financial(symbol, force)

    def sync_company(self, symbol, years=5, max_pages=100, force=False):
        with _sync_lock(str(self.repository.path.resolve()), normalize(symbol)):
            return self.provider.sync_company(symbol, years=years, max_pages=max_pages, force=force)

    def _sync_financial(self, symbol, force=False):
        from .financial_history import settings
        config = settings()
        repo = self.repository
        if not force and repo.fresh(symbol, "KODAL", config["sync_ttl_seconds"]):
            return dict(repo.state(symbol, "KODAL"), reused_local=True)
        state = repo.state(symbol, "KODAL")
        result = {"source": "KODAL", "symbol": symbol, "inserted": 0, "updated": 0,
                  "skipped": 0, "rejected": [], "records_received": 0,
                  "cursor": state.get("cursor"), "status": "SUCCESS",
                  "last_sync_date": state.get("last_sync_date")}
        try:
            # Retry rejected/missing old periods by metadata discovery; known
            # documents are still skipped, so no full report re-download occurs.
            annual = [r for r in repo.reports(symbol) if r["report_type"] == "annual"]
            fiscal_years = {int(r["period"][:4]) for r in annual}
            expected = set(range(max(fiscal_years) - config["years"] + 1, max(fiscal_years) + 1)) if fiscal_years else set()
            covered = len(fiscal_years) >= config["years"] and expected <= fiscal_years
            cursor = state.get("cursor") if covered and not state.get("rejected") else None
            batch = self.provider.fetch(symbol, repo.known_documents(symbol), cursor, config["years"])
            result["records_received"] = len(batch["reports"])
            result["rejected"] = list(batch["rejected"])
            for report, raw in batch["reports"]:
                try:
                    result[repo.save_report(report, raw)] += 1
                except (ValueError, KeyError, TypeError) as exc:
                    result["rejected"].append({"document_id": report.get("document_id"), "error": str(exc)})
            if result["rejected"]:
                result["status"] = "PARTIAL"
            else:
                result["cursor"] = batch["cursor"]
                result["last_sync_date"] = now()
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError) as exc:
            result["status"] = "SOURCE_UNAVAILABLE"
            result["error"] = str(exc)
        return repo.record_sync(symbol, "KODAL", result)


@lru_cache(maxsize=None)
def _sync_lock(path, symbol):
    return Lock()


# One implementation, two documented names; no parallel sync service.
KodALSyncManager = HistoricalDataSyncManager


def connection_test(symbol, output_dir, *, client=None, attempts=2, timeout=12,
                    resolver=None):
    """Real-source acceptance probe. Never promotes HTTP success to parser success.

    Artifacts are diagnostic evidence, separate from the operational database.
    Endpoint is the existing project's candidate, not assumed verified.
    """
    import hashlib
    import socket
    from pathlib import Path
    from time import monotonic
    from .financial_history import HistoricalDataRepository

    if not 1 <= attempts <= 3 or not 0 < timeout <= 60:
        raise ValueError("Probe limits: 1–3 attempts and timeout <= 60 seconds")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stages = {name: "NOT_RUN" for name in (
        "connection", "search", "issuer_identification", "report_discovery",
        "report_download", "parsing", "extraction", "validation", "local_save", "local_reload")}
    result = {"test": "KODAL_CONNECTION_TEST", "symbol": normalize(symbol),
              "company": None, "started_at": now(), "stages": stages,
              "dns": {}, "requests": [], "reports_downloaded": 0,
              "records_saved": 0, "calculated_records": 0,
              "endpoint": CodalHistoricalProvider.search_url,
              "endpoint_verified": False, "timeout_seconds": timeout,
              "maximum_attempts": attempts, "status": "FAIL"}
    resolver = resolver or socket.getaddrinfo
    for host in ("www.codal.ir", "search.codal.ir"):
        try:
            addresses = resolver(host, 443, type=socket.SOCK_STREAM)
            result["dns"][host] = {"status": "PASS", "addresses": sorted({a[4][0] for a in addresses})}
        except OSError as exc:
            result["dns"][host] = {"status": "FAIL", "error_type": type(exc).__name__}

    owned = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=False,
                                   headers={"User-Agent": "Mozilla/5.0 SMART connection test"})

    def request(url, name, params=None):
        for attempt in range(1, attempts + 1):
            started = monotonic()
            log = {"stage": name, "url": url, "attempt": attempt}
            try:
                response = client.get(url, params=params, timeout=timeout)
                log.update(status_code=response.status_code,
                           content_type=response.headers.get("content-type"),
                           encoding=response.encoding, bytes=len(response.content),
                           content_hash=hashlib.sha256(response.content).hexdigest())
                response.raise_for_status()
                (output / f"{name}.raw").write_bytes(response.content)
                return response
            except httpx.HTTPError as exc:
                log.update(error_type=type(exc).__name__, timeout=isinstance(exc, httpx.TimeoutException))
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code not in {408, 429}:
                    break
            finally:
                log["elapsed_seconds"] = round(monotonic() - started, 3)
                result["requests"].append(log)
        return None

    try:
        homepage = request("https://www.codal.ir/", "homepage")
        stages["connection"] = "PASS" if homepage is not None else "FAIL"
        response = request(result["endpoint"], "search", {"Symbol": symbol, "PageNumber": 1,
                           "Category": 1, "Length": 12, "IsAudited": True, "IsNotAudited": True})
        if response is None:
            stages["search"] = "FAIL"
            return result
        stages["connection"] = "PASS"
        try:
            response.content.decode(response.encoding or "utf-8", errors="strict")
            data = response.json()
            letters = data.get("Letters") if isinstance(data, dict) else None
            if not isinstance(letters, list) or any(not isinstance(x, dict) for x in letters):
                raise ValueError("Expected Letters array of objects")
        except (ValueError, UnicodeError) as exc:
            stages["search"] = "FAIL"
            result["format_error"] = str(exc)
            return result
        stages["search"] = "PASS"
        result["endpoint_verified"] = True
        matching = [x for x in letters if normalize(x.get("Symbol", "")) == normalize(symbol)]
        if not matching:
            stages["issuer_identification"] = "FAIL"
            return result
        names = {normalize(x.get("CompanyName", "")) for x in matching if x.get("CompanyName")}
        if len(names) != 1:
            stages["issuer_identification"] = "FAIL"
            result["issuer_error"] = "Missing or conflicting issuer names"
            return result
        result["company"] = names.pop()
        stages["issuer_identification"] = "PASS"
        candidates = [x for x in matching if issuer_report(x, symbol) and "صورت" in normalize(x.get("Title", ""))
                      and "مالی" in normalize(x.get("Title", "")) and x.get("TracingNo") and x.get("Url")]
        if not candidates:
            stages["report_discovery"] = "FAIL"
            return result
        letter = candidates[0]
        (output / "announcement.json").write_text(json.dumps(letter, ensure_ascii=False, indent=2), encoding="utf-8")
        url = urljoin("https://www.codal.ir/", letter["Url"])
        if not source_url(url):
            stages["report_discovery"] = "FAIL"
            return result
        stages["report_discovery"] = "PASS"
        result["report_id"] = str(letter["TracingNo"])
        document = request(url, "report")
        if document is None:
            stages["report_download"] = "FAIL"
            return result
        stages["report_download"] = "PASS"
        result["reports_downloaded"] = 1
        # An HTML report download is not a PDF/Excel acceptance pass.
        result["download_format"] = document.headers.get("content-type")
        links = statement_links(document.text, url, consolidated="تلفیقی" in normalize(letter["Title"]))
        if links:
            # Probe one explicitly identified income sheet before broad extraction.
            label, sheet_url = next(((label, link) for label, link in links if "سود و زیان" in label), links[0])
            sheet = request(sheet_url, "statement")
            if sheet is None:
                stages["report_download"] = "FAIL"
                return result
            result["statement_label"] = label
            result["statement_url"] = sheet_url
            document, url = sheet, sheet_url
        try:
            raw = document.content.decode(document.encoding or "utf-8", errors="strict")
            report = parse_document(letter, raw, symbol, url)
        except (ValueError, KeyError, TypeError) as exc:
            stages["parsing"] = "FAIL"
            result["parse_error"] = str(exc)
            return result
        stages["parsing"] = "PASS"
        extracted = sum(m["value"] is not None for m in report["metrics"].values())
        stages["extraction"] = "PASS" if extracted else "FAIL"
        if not extracted:
            return result
        result["extracted_records"] = extracted
        result["missing_metrics"] = [m for m in METRICS if report["metrics"].get(m, {}).get("value") is None]
        repo = HistoricalDataRepository(output / "acceptance.sqlite3")
        try:
            saved = repo.save_report(report, raw)
        except (ValueError, KeyError, TypeError) as exc:
            stages["validation"] = "FAIL"
            result["validation_error"] = str(exc)
            return result
        stages["validation"] = stages["local_save"] = "PASS"
        result["storage_action"] = saved
        result["records_saved"] = len(report["metrics"]) if saved != "skipped" else 0
        reopened = HistoricalDataRepository(output / "acceptance.sqlite3")
        stages["local_reload"] = "PASS" if str(letter["TracingNo"]) in reopened.known_documents(symbol) else "FAIL"
        result["status"] = "PASS" if all(s == "PASS" for s in stages.values()) else "FAIL"
        return result
    finally:
        if owned:
            client.close()
        result["finished_at"] = now()
        (output / "connection_test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
