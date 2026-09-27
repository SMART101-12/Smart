"""Typed notice boundary using the existing Codal transport and source rules."""
from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Any, Callable
from urllib.parse import urljoin

import httpx

from smart.codal import CodalHistoricalProvider, issuer_report
from smart.financial_history import normalize, source_url


@dataclass(frozen=True)
class CodalNotice:
    symbol: str
    title: str
    date: str
    pdf_url: str | None
    content_summary: str
    report_id: str
    attachment_url: str | None = None


class CodalClient:
    def __init__(self, client: httpx.Client, *, wait: Callable[[float], None] = sleep,
                 attempts: int = 3) -> None:
        if not 1 <= attempts <= 5:
            raise ValueError("attempts must be between 1 and 5")
        self.client = client
        self.wait = wait
        self.attempts = attempts

    def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        for attempt in range(self.attempts):
            try:
                response = self.client.get(url, params=params, follow_redirects=False, timeout=15)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {408, 429, 500, 502, 503, 504} or attempt + 1 == self.attempts:
                    raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt + 1 == self.attempts:
                    raise
            self.wait(min(2 ** attempt * .25, 2.))
        raise RuntimeError("Unreachable retry state")

    @staticmethod
    def _link(value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        url = urljoin("https://www.codal.ir/", value)
        if not source_url(url):
            raise ValueError("Untrusted Codal attachment URL")
        return url

    def notices(self, symbol: str, *, max_pages: int = 100) -> list[CodalNotice]:
        if not 1 <= max_pages <= 100:
            raise ValueError("max_pages must be 1..100")
        result: dict[str, CodalNotice] = {}
        seen: set[tuple[str, ...]] = set()
        for page in range(1, max_pages + 1):
            response = self._get(CodalHistoricalProvider.search_url,
                                 {"Symbol": symbol, "PageNumber": page})
            data = response.json()
            letters = data.get("Letters") if isinstance(data, dict) else None
            if not isinstance(letters, list) or any(not isinstance(x, dict) for x in letters):
                raise ValueError("Invalid Codal notice response")
            if not letters:
                return list(result.values())
            fingerprint = tuple(str(x.get("TracingNo", "")) for x in letters)
            if fingerprint in seen:
                raise ValueError("Repeated Codal page; incomplete discovery")
            seen.add(fingerprint)
            for letter in letters:
                if not issuer_report(letter, symbol):
                    continue
                if not letter.get("TracingNo") or not letter.get("Title") or not letter.get("PublishDateTime"):
                    raise ValueError("Notice identity/title/date missing")
                notice = CodalNotice(normalize(symbol), normalize(letter["Title"]),
                    normalize(letter["PublishDateTime"]), self._link(letter.get("PdfUrl")),
                    normalize(letter.get("Summary") or ""), str(letter["TracingNo"]),
                    self._link(letter.get("AttachmentUrl")))
                result[notice.report_id] = notice
            total = data.get("TotalPages", data.get("Page"))
            if type(total) is int and total >= 1 and page >= total:
                return list(result.values())
        raise ValueError("Codal page budget exhausted; incomplete discovery")

    def attachment(self, url: str) -> bytes:
        if not source_url(url):
            raise ValueError("Untrusted Codal attachment URL")
        for _ in range(4):
            try:
                response = self._get(url)
                if not response.content:
                    raise ValueError("Empty Codal attachment")
                return response.content
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {301, 302, 303, 307, 308}:
                    raise
                target = urljoin(url, exc.response.headers.get("location", ""))
                if not source_url(target) or target == url:
                    raise ValueError("Untrusted or empty attachment redirect") from exc
                url = target
        raise ValueError("Attachment redirect limit exceeded")
