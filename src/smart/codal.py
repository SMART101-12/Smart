"""Read-only Codal acquisition with conservative, evidence-preserving parsing.

Unsupported layouts are rejected, never approximated. Report columns require
an explicit fiscal end date; comparative columns cannot become current values.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from threading import Lock
from urllib.parse import urljoin

import httpx

from .financial_history import METRICS, normalize, number, now, period_date, source_url


from .codal_parser import (
    ALIASES, PARSER_VERSION, CodalChallengeError, Tables, embedded_tables,
    fiscal_columns, is_verification_page, issuer_report, metric_label,
    parse_document, statement_links,
)


class CodalHistoricalProvider:
    search_url = "https://search.codal.ir/api/search/v2/q"

    def __init__(self, client=None, repository=None, fallback_client: httpx.Client | None = None):
        self.client = client
        self.repository = repository
        self.fallback_client = fallback_client
        self.challenge_url: str | None = None
        self.challenge_supported = False
        self.deadline = time.monotonic() + 120

    def get(self, url, *, params=None):
        """Bounded retries; follow only official report redirects."""
        cooldown = self.repository.state("__SOURCE__", "KODAL_HTTP") if self.repository else {}
        retry_at = cooldown.get("retry_at")
        if retry_at and datetime.fromisoformat(retry_at) > datetime.now(timezone.utc):
            raise httpx.HTTPError("HTTP 429: Codal cooldown until " + retry_at)
        for attempt in range(3):
            try:
                for _ in range(4):
                    remaining = self.deadline - time.monotonic()
                    if remaining <= 0:
                        raise httpx.TimeoutException("Codal acquisition budget exceeded")
                    read_timeout = self.client.timeout.read or 20
                    response = self.client.get(url, params=params, timeout=min(read_timeout, remaining))
                    if response.status_code in {301, 302, 303, 307, 308}:
                        target = urljoin(str(response.url), response.headers.get("location", ""))
                        if not source_url(target):
                            raise ValueError("Untrusted report redirect")
                        url, params = target, None
                        continue
                    if response.status_code == 429:
                        raw_retry = response.headers.get("Retry-After", "")
                        try:
                            seconds = float(raw_retry)
                        except ValueError:
                            try:
                                deadline = parsedate_to_datetime(raw_retry)
                                if deadline.tzinfo is None:
                                    deadline = deadline.replace(tzinfo=timezone.utc)
                                seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
                            except (ValueError, TypeError, OverflowError):
                                seconds = 300
                        seconds = max(1, min(seconds, 86400)) if math.isfinite(seconds) else 300
                        if self.repository:
                            self.repository.record_sync("__SOURCE__", "KODAL_HTTP", {
                                "status": "RATE_LIMITED", "http_status": 429,
                                "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
                                "retry_after_seconds": seconds})
                    response.raise_for_status()
                    if is_verification_page(response.text):
                        self.challenge_url = str(response.url)
                        self.challenge_supported = all(path in response.text for path in (
                            "/ReportsCaptcha.aspx/GetCaptchaImage", "/ReportsCaptcha.aspx/VerifyCaptcha"))
                        raise CodalChallengeError("USER_ACTION_REQUIRED: Codal returned a verification page, not report data")
                    return response
                raise ValueError("Too many report redirects")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
                if self.fallback_client is not None:
                    self.client = self.fallback_client
            except httpx.HTTPStatusError as exc:
                if attempt == 2 or exc.response.status_code < 500:
                    raise
            time.sleep(min(0.25 * 2 ** attempt, max(0, self.deadline - time.monotonic())))

    def download(self, symbol, docid, url, refresh=False):
        cached = self.repository.asset(symbol, docid, url) if self.repository and not refresh else None
        if cached:
            raw = cached["payload"].decode("utf-8-sig", errors="strict")
            if not is_verification_page(raw):
                return raw
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
        if results:
            return results
        # Some announcements titled "financial statements" resolve only to an
        # auditor's narrative. It has no statement grid and is not a failed
        # numerical extraction or a missing financial year.
        parser = Tables()
        parser.feed(raw)
        if (not embedded_tables(raw) and any(
                row and "گزارش حسابرس مستقل" in row[0]
                for table in parser.tables for row in table[:2])):
            return []
        return [(parse_document(letter, raw, symbol, url), raw)]

    def fetch(self, symbol, known_ids, publication_cursor=None, years=5):
        """Discover announcements; only download unknown reports.

        The publication cursor (not fiscal year) discovers amendments to older
        periods. Initial discovery is bounded; incomplete pagination is explicit.
        """
        self.deadline = time.monotonic() + 120
        if self.client is None:
            with httpx.Client(timeout=12, follow_redirects=False,
                              headers={"User-Agent": "Mozilla/5.0 SMART"}) as client, \
                    httpx.Client(timeout=12, trust_env=False, follow_redirects=False,
                                 headers={"User-Agent": "Mozilla/5.0 SMART"}) as direct:
                return CodalHistoricalProvider(client, self.repository, direct).fetch(symbol, known_ids, publication_cursor, years)
        output, rejected, periods, excluded = [], [], set(), []
        existing = self.repository.reports(symbol) if self.repository else []
        latest_year = max((int(r["period"][:4]) for r in existing
                           if r["report_type"] == "annual"), default=None)
        discovered_years = set()
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
                if not ("12 ماهه" in title or "سال مالی" in title) or "صورت" not in title or "مالی" not in title:
                    continue
                fiscal = re.search(r"منتهی به\s*(1[34]\d{2})/\d{2}/\d{2}", title)
                if fiscal:
                    fiscal_year = int(fiscal[1])
                    latest_year = max(latest_year or fiscal_year, fiscal_year)
                    if fiscal_year < latest_year - years:
                        excluded.append({"document_id": docid, "fiscal_year": fiscal_year,
                                         "reason": "outside_requested_financial_window"})
                        continue
                    discovered_years.add(fiscal_year)
                if docid in downloaded and not changed:
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
            if not publication_cursor and len(discovered_years) >= years + 1:
                break
        else:
            rejected.append({"error": "Codal pagination limit reached; discovery incomplete"})
        return {"reports": output, "rejected": rejected, "cursor": newest,
                "excluded_documents": excluded,
                "discovery_scope": {"latest_fiscal_year": latest_year,
                                    "minimum_fiscal_year": latest_year - years if latest_year else None,
                                    "years_requested": years}}

    def sync_company(self, symbol, *, years=5, max_pages=100, force=False):
        self.deadline = time.monotonic() + 120
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
            with httpx.Client(timeout=12, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 SMART"}) as client, \
                    httpx.Client(timeout=12, trust_env=False, follow_redirects=False,
                                 headers={"User-Agent": "Mozilla/5.0 SMART"}) as direct:
                return CodalHistoricalProvider(client, repo, direct).sync_company(symbol, years=years, max_pages=max_pages, force=force)
        state = repo.state(symbol, "KODAL_COMPANY")
        if not force and state.get("action_required") == "CODAL_USER_VERIFICATION":
            return dict(state, reused_local=True)
        if (not force and state.get("parser_version") == PARSER_VERSION
                and state.get("status") == "SUCCESS"
                and repo.fresh(symbol, "KODAL_COMPANY", settings()["sync_ttl_seconds"])):
            return dict(state, reused_local=True)
        current_parser = state.get("parser_version") == PARSER_VERSION
        cursor = state.get("cursor") if current_parser and state.get("status") == "SUCCESS" else None
        result = {"symbol": normalize(symbol), "source": "KODAL", "status": "SUCCESS",
                  "parser_version": PARSER_VERSION,
                  "inserted": 0, "updated": 0, "skipped": 0, "discovered": 0,
                  "rejected": [], "pages": [], "cursor": cursor,
                  "last_sync_date": state.get("last_sync_date")}
        known = repo.known_documents(symbol) | {r["report_id"] for r in repo.monthly_sales(symbol, selected=False)}
        pending_changed = set(state.get("pending_changed", []))
        if not current_parser:
            known = set()
        newest = cursor
        started = time.monotonic()
        verification_required = False
        for category_index, category in enumerate((3, 1), start=1):
            # Reserve time for both report families; one slow family must not starve the other.
            self.deadline = started + 60 * category_index
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
                    verification_required = isinstance(exc, CodalChallengeError)
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
                    if time.monotonic() >= self.deadline:
                        result["rejected"].append({"category": category, "page": page,
                                                   "error": "Acquisition budget reached; resume required"})
                        break
                    if not issuer_report(letter, symbol):
                        continue
                    title = normalize(letter.get("Title", ""))
                    financial = ("صورت" in title and "مالی" in title
                                 and ("حسابرسی شده" in title or "حسابرسی نشده" in title))
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
                    if changed:
                        pending_changed.add(docid)
                    changed = docid in pending_changed
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
                        pending_changed.discard(docid)
                    except (ValueError, TypeError, KeyError, httpx.HTTPError) as exc:
                        result["rejected"].append({"report_id": docid, "source_url": url, "error": str(exc)})
                        if isinstance(exc, CodalChallengeError):
                            verification_required = True
                            break
                if verification_required or time.monotonic() >= self.deadline:
                    break
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
            if verification_required:
                result["action_required"] = "CODAL_USER_VERIFICATION"
                result["blocked_url"] = self.challenge_url
                break
        result["pending_changed"] = sorted(pending_changed)
        result["status"] = "PARTIAL" if result["rejected"] else "SUCCESS"
        if result["rejected"]:
            result["error"] = result["rejected"][0]["error"]
        if result["status"] == "SUCCESS":
            result["cursor"], result["last_sync_date"] = newest, now()
        datasets = company_dataset(repo, symbol)
        for name in ("quarterly_financials", "quarterly_sales", "trend_metrics", "seasonality", "data_quality"):
            repo.save_calculated_dataset(symbol, name, datasets[name])
        result["data_quality"] = datasets["data_quality"]
        repo.record_sync(symbol, "KODAL", result)
        return repo.record_sync(symbol, "KODAL_COMPANY", result)


class HistoricalDataSyncManager:
    def __init__(self, repository, provider=None):
        self.repository = repository
        self.provider = provider or CodalHistoricalProvider(repository=repository)

    def sync_financial(self, symbol, force=False):
        if not force:
            cached = self._cached_financial(symbol)
            if cached:
                return cached
        with _sync_lock(str(self.repository.path.resolve()), normalize(symbol)):
            return self._sync_financial(symbol, force)

    def _cached_financial(self, symbol):
        from datetime import datetime, timezone
        from .financial_history import settings

        config = settings()
        repo = self.repository
        state = repo.state(symbol, "KODAL")
        if state.get("parser_version") != PARSER_VERSION:
            return None
        if repo.fresh(symbol, "KODAL", config["sync_ttl_seconds"]):
            return dict(state, reused_local=True)
        if state.get("status") not in {"PARTIAL", "SOURCE_UNAVAILABLE"}:
            return None
        try:
            requested = datetime.fromisoformat(state["request_date"])
            recent = (datetime.now(timezone.utc) - requested).total_seconds() < config["sync_ttl_seconds"]
        except (KeyError, TypeError, ValueError):
            return None
        if not recent:
            return None
        years = {int(r["period"][:4]) for r in repo.reports(symbol)
                 if r["report_type"] == "annual"}
        return dict(state, reused_local=True) if len(years) >= config["years"] else None

    def sync_company(self, symbol, years=5, max_pages=100, force=False):
        with _sync_lock(str(self.repository.path.resolve()), normalize(symbol)):
            if self.provider.client is None:
                from .codal_access import access_session
                with access_session(self.repository, symbol) as access:
                    assert access is not None
                    return access.provider.sync_company(symbol, years=years, max_pages=max_pages, force=force)
            return self.provider.sync_company(symbol, years=years, max_pages=max_pages, force=force)

    def _sync_financial(self, symbol, force=False):
        from .financial_history import settings
        config = settings()
        repo = self.repository
        if not force:
            cached = self._cached_financial(symbol)
            if cached:
                return cached
        state = repo.state(symbol, "KODAL")
        result = {"source": "KODAL", "symbol": symbol, "inserted": 0, "updated": 0,
                  "parser_version": PARSER_VERSION,
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
            current_parser = state.get("parser_version") == PARSER_VERSION
            cursor = state.get("cursor") if current_parser and covered and not state.get("rejected") else None
            known = repo.known_documents(symbol) if current_parser else set()
            batch = self.provider.fetch(symbol, known, cursor, config["years"])
            result["records_received"] = len(batch["reports"])
            result["rejected"] = list(batch["rejected"])
            result["excluded_documents"] = batch.get("excluded_documents", [])
            result["discovery_scope"] = batch.get("discovery_scope")
            for report, raw in batch["reports"]:
                try:
                    result[repo.save_report(report, raw)] += 1
                except (ValueError, KeyError, TypeError) as exc:
                    result["rejected"].append({"document_id": report.get("document_id"), "error": str(exc)})
            if result["rejected"]:
                result["status"] = "PARTIAL"
                result["error"] = result["rejected"][0]["error"]
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
