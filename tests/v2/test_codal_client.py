import httpx
import pytest
from smart_v2.acquisition.codal import CodalClient


def letter(n: int) -> dict:
    return {"Symbol": "كيان", "Title": "گزارش ۱۴۰۴", "PublishDateTime": "۱۴۰۵/۰۱/۰۱",
            "TracingNo": n, "PdfUrl": "/report.pdf", "AttachmentUrl": "/attachment"}


def test_retry_pagination_encoding_and_attachment() -> None:
    calls, waits = [], []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1: return httpx.Response(503)
        if request.url.path == '/report.pdf': return httpx.Response(200, content=b'%PDF-test')
        page = int(request.url.params['PageNumber'])
        return httpx.Response(200, json={"Letters": [letter(page)], "TotalPages": 2})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = CodalClient(http, wait=waits.append)
        notices = client.notices("کیان")
        assert len(notices) == 2 and notices[0].symbol == "کیان"
        assert notices[0].date == "1405/01/01" and notices[0].content_summary == ""
        assert waits == [.25]
        assert client.attachment(notices[0].pdf_url) == b'%PDF-test'


def test_timeout_and_invalid_response_do_not_fabricate_notices() -> None:
    waits = []
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("offline")
    with httpx.Client(transport=httpx.MockTransport(down)) as http:
        with pytest.raises(httpx.ReadTimeout): CodalClient(http, wait=waits.append).notices("TEST")
    assert waits == [.25, .5]
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='<html>error</html>'))) as http:
        with pytest.raises(ValueError): CodalClient(http).notices("TEST")


def test_repeated_pages_and_unsafe_attachments_rejected() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"Letters": [letter(1)]}))) as http:
        client = CodalClient(http)
        with pytest.raises(ValueError, match="Repeated"): client.notices("کیان")
        with pytest.raises(ValueError, match="Untrusted"): client.attachment('https://evil.test/report.pdf')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'Location':'https://evil.test/a'}))) as http:
        with pytest.raises(ValueError, match="Untrusted"): CodalClient(http).attachment('https://www.codal.ir/a')
