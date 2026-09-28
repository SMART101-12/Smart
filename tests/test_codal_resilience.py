from datetime import datetime, timedelta, timezone

import httpx
import pytest

from smart.codal import CodalHistoricalProvider, parse_document, statement_links
from smart.financial_history import HistoricalDataRepository


def test_side_by_side_balance_sheet_uses_each_description_block():
    letter = {"Symbol": "TEST", "Title": "صورتهای مالی 12 ماهه منتهی به 1404/12/29 حسابرسی شده",
              "TracingNo": "balance", "PublishDateTime": "1405/03/01"}
    raw = '''میلیون ریال<table><tr><th>شرح</th><th>1404/12/29</th><th>1403/12/29</th>
    <th>شرح</th><th>1404/12/29</th><th>1403/12/29</th></tr>
    <tr><td>جمع دارایی ها</td><td>100</td><td>90</td><td>جمع بدهی ها</td><td>40</td><td>35</td></tr>
    <tr><td>دارایی های جاری</td><td></td><td></td><td>سرمایه</td><td>30</td><td>20</td></tr>
    <tr><td>جمع دارایی های جاری</td><td>70</td><td>60</td><td></td><td></td><td></td></tr>
    <tr><td></td><td></td><td></td><td>حقوق صاحبان سهام</td><td>60</td><td>55</td></tr></table>'''
    report = parse_document(letter, raw, "TEST", "https://www.codal.ir/Reports/example")
    assert report["metrics"]["assets"]["value"] == 100
    assert report["metrics"]["liabilities"]["value"] == 40
    assert report["metrics"]["equity"]["value"] == 60
    assert report["metrics"]["current_assets"]["value"] == 70
    assert report["metrics"]["liabilities"]["locator"].endswith("column:4")


def test_legacy_sheet_links_use_advertised_ids():
    raw = '''<select id="ddlTable"><option value="0">ترازنامه</option>
    <option value="9">جریان وجوه نقد</option>
    <option value="12">ترازنامه تلفيقي</option></select>'''
    assert len(statement_links(raw, "https://www.codal.ir/report", False)) == 2
    assert statement_links(raw, "https://www.codal.ir/report", True)[0][1].endswith("sheetId=12")


def test_rate_limit_is_not_retried_and_cooldown_is_shared_across_symbols(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "db.sqlite")
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(429, headers={"Retry-After": "600"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = CodalHistoricalProvider(client, repo)
        with pytest.raises(httpx.HTTPStatusError):
            first.get(first.search_url, params={"Symbol": "FIRST"})
        second = CodalHistoricalProvider(client, HistoricalDataRepository(repo.path))
        with pytest.raises(httpx.HTTPError, match="cooldown"):
            second.get(second.search_url, params={"Symbol": "SECOND"})
    assert len(calls) == 1
    state = repo.state("__SOURCE__", "KODAL_HTTP")
    assert state["retry_after_seconds"] == 600
    assert datetime.fromisoformat(state["retry_at"]) > datetime.now(timezone.utc)


def test_expired_cooldown_allows_a_new_request(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "db.sqlite")
    repo.record_sync("__SOURCE__", "KODAL_HTTP", {
        "retry_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        assert CodalHistoricalProvider(client, repo).get("https://www.codal.ir/report").status_code == 200
