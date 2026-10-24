from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from smart.codal import CodalHistoricalProvider, PARSER_VERSION, statement_links
from smart.codal_operations import parse_monthly
from smart.company_financials import company_dataset
from smart.financial_history import HistoricalDataRepository


def announcement(doc: str, months: int = 3) -> dict:
    return {"Symbol": "TEST", "CompanyName": "TEST", "TracingNo": doc,
            "Title": f"صورت‌های مالی دوره {months} ماهه منتهی به 1404/03/31 حسابرسی نشده",
            "PublishDateTime": "1404/04/20", "Url": "/Reports/" + doc}


def statement(value: int = 100) -> str:
    return f'''میلیون ریال<span id="ctl00_lblYearEndToDate">1404/12/29</span>
    <table><tr><th>شرح</th><th>1404/03/31</th><th>1403/03/31</th></tr>
    <tr><td>درآمدهای عملیاتی</td><td>{value}</td><td>60</td></tr></table>'''


def monthly_letter() -> dict:
    return {"Symbol": "TEST", "CompanyName": "TEST", "TracingNo": "monthly",
            "Title": "گزارش فعالیت ماهانه دوره ۱ ماهه منتهی به ۱۴۰۴/۰۳/۳۱",
            "PublishDateTime": "1404/04/05", "Url": "/Reports/monthly"}


MONTHLY = '''<table><tr><th></th><th></th><th colspan="3">دوره یک ماهه منتهی به 1404/03/31</th>
<th>از ابتدای سال</th></tr><tr><th>نام محصول</th><th>واحد</th><th>مقدار تولید</th>
<th>مقدار فروش</th><th>مبلغ فروش (میلیون ریال)</th><th>مبلغ فروش (میلیون ریال)</th></tr>
<tr><td>فروش داخلی</td></tr><tr><td>محصول الف</td><td>تن</td><td>12</td><td>10</td><td>100</td><td>900</td></tr>
<tr><td>جمع</td><td></td><td></td><td></td><td>100</td><td>900</td></tr></table>'''


def test_live_style_prefixed_selector_follows_all_advertised_sheets() -> None:
    html = '''<select id="ctl00_ddlTable"><option value="19" selected="selected">نظر حسابرس</option>
    <option value="1">صورت سود و زیان</option><option value="0">صورت وضعیت مالی</option>
    <option value="9">صورت جریان های نقدی</option><option value="13">صورت سود و زیان تلفیقی</option></select>'''
    links = statement_links(html, "https://www.codal.ir/Reports/Decision.aspx?x=1", False)
    assert len(links) == 3
    assert links[0][1].endswith("x=1&sheetId=1")
    raw = html.replace('<option value="13">صورت سود و زیان تلفیقی</option>', '')
    def standalone(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=statement() if "sheetId" in request.url.params else raw)
    with httpx.Client(transport=httpx.MockTransport(standalone)) as sheet_client:
        reports = CodalHistoricalProvider(sheet_client).download_statements(
            announcement("quarter"), "TEST", "https://www.codal.ir/Reports/quarter")
    assert len(reports) == 1
    assert reports[0][0]["metrics"]["revenue"]["value"] == 100
    assert '"codal_bundle": 1' in reports[0][1]


def test_transport_fallback_is_only_for_network_failure() -> None:
    calls = []
    def broken(request: httpx.Request) -> httpx.Response:
        calls.append("proxy")
        raise httpx.RemoteProtocolError("disconnected")
    def direct(request: httpx.Request) -> httpx.Response:
        calls.append("direct")
        return httpx.Response(200, json={"Letters": []})
    with httpx.Client(transport=httpx.MockTransport(broken)) as primary, httpx.Client(transport=httpx.MockTransport(direct)) as fallback:
        assert CodalHistoricalProvider(primary, fallback_client=fallback).get("https://www.codal.ir").status_code == 200
    assert calls == ["proxy", "direct"]


def test_verification_page_never_becomes_cached_report_and_stops_sync(tmp_path) -> None:
    repo = HistoricalDataRepository(tmp_path / "challenge.db")
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "search.codal.ir":
            return httpx.Response(200, json={"Letters": [monthly_letter(), dict(monthly_letter(), TracingNo="other")], "TotalPages": 1})
        return httpx.Response(200, text='<title>تأیید کاربر</title><input id="captchaCode">')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CodalHistoricalProvider(client, repo).sync_company("TEST")
    assert result["status"] == "PARTIAL" and result["action_required"] == "CODAL_USER_VERIFICATION"
    assert len(calls) == 2
    assert repo.asset("TEST", "monthly", "https://www.codal.ir/Reports/monthly") is None
    assert repo.monthly_sales("TEST") == []


def test_old_cached_challenge_is_not_reused_as_financial_data(tmp_path) -> None:
    repo = HistoricalDataRepository(tmp_path / "old-challenge.db")
    url = "https://www.codal.ir/Reports/monthly"
    repo.save_asset("TEST", "monthly", url, b'<input id="captchaCode">', "text/html")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=MONTHLY))) as client:
        assert CodalHistoricalProvider(client, repo).download("TEST", "monthly", url) == MONTHLY


def test_rate_limit_does_not_switch_to_alternative_transport() -> None:
    def forbidden_fallback(request: httpx.Request) -> httpx.Response:
        pytest.fail("Must honor rate limit instead of switching transport")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as client, \
            httpx.Client(transport=httpx.MockTransport(forbidden_fallback)) as fallback:
        with pytest.raises(httpx.HTTPStatusError):
            CodalHistoricalProvider(client, fallback_client=fallback).get("https://www.codal.ir")


def test_company_sync_extracts_monthly_and_interim_and_reuses_success(tmp_path) -> None:
    repo = HistoricalDataRepository(tmp_path / "company.db")
    requests = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host == "search.codal.ir":
            letter = monthly_letter() if request.url.params["Category"] == "3" else announcement("quarter")
            return httpx.Response(200, json={"Letters": [letter], "TotalPages": 1})
        return httpx.Response(200, text=MONTHLY if request.url.path.endswith("monthly") else statement())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = CodalHistoricalProvider(client, repo)
        result = provider.sync_company("TEST")
        assert result["status"] == "SUCCESS"
        assert result["inserted"] == 2 and result["parser_version"] == PARSER_VERSION
        count = len(requests)
        assert provider.sync_company("TEST")["reused_local"]
        assert len(requests) == count
    data = company_dataset(repo, "TEST")
    assert data["monthly_sales"][0]["sales_value"]["value"] == 100_000_000
    assert data["quarterly_financials"][0]["metrics"]["revenue"]["value"] == 100_000_000
    assert data["data_quality"]["source_status"] == "SUCCESS"
    before = company_dataset(repo, "TEST", as_of=date(2025, 6, 22))
    assert before["monthly_sales"] == [] and before["financial_data"] == []


def test_monthly_current_column_not_cumulative_and_restated_as_of(tmp_path) -> None:
    repo = HistoricalDataRepository(tmp_path / "monthly.db")
    original = monthly_letter()
    parsed = parse_monthly(original, MONTHLY, "TEST", "https://www.codal.ir/Reports/monthly")
    repo.save_monthly(parsed, MONTHLY)
    amended = dict(original, TracingNo="amended", PublishDateTime="1404/06/01", Title=original["Title"] + " (اصلاحیه)")
    changed = MONTHLY.replace("100</td>", "120</td>")
    repo.save_monthly(parse_monthly(amended, changed, "TEST", "https://www.codal.ir/Reports/amended"), changed)
    assert company_dataset(repo, "TEST")["monthly_sales"][0]["sales_value"]["value"] == 120_000_000
    historical = company_dataset(repo, "TEST", as_of=date(2025, 7, 1))
    assert historical["monthly_sales"][0]["sales_value"]["value"] == 100_000_000
    assert historical["product_sales"][0]["report_id"] == "monthly"


def test_company_endpoint_reads_local_evidence_without_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SMART_HISTORICAL_DB", str(tmp_path / "api.db"))
    from smart.webapp import app
    with TestClient(app) as client:
        response = client.get("/api/company-reports", params={"symbol": "TEST"})
        assert response.status_code == 200 and response.json()["monthly_sales"] == []
        assert client.get("/financial-reports").status_code == 200
        assert client.get("/codal-reports.js").status_code == 200


def test_user_verifies_same_session_then_resume_saves_and_never_redownloads(tmp_path, monkeypatch) -> None:
    from smart import codal_access
    from smart.codal import HistoricalDataSyncManager
    from smart.webapp import app
    monkeypatch.setenv("SMART_HISTORICAL_DB", str(tmp_path / "assisted.db"))
    calls = []
    verified = False
    challenge = '''<input id="captchaCode"><script>
    fetch('/ReportsCaptcha.aspx/GetCaptchaImage'); fetch('/ReportsCaptcha.aspx/VerifyCaptcha');</script>'''

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal verified
        calls.append((request.method, request.url.path))
        if request.url.host == "search.codal.ir":
            return httpx.Response(200, json={"Letters": [monthly_letter()] if request.url.params["Category"] == "3" else [], "TotalPages": 1})
        if request.url.path.endswith("GetCaptchaImage"):
            assert "challenge=abc" in request.headers.get("cookie", "")
            return httpx.Response(200, json={"d": "data:image/png;base64,aW1hZ2U="})
        if request.url.path.endswith("VerifyCaptcha"):
            assert "challenge=abc" in request.headers.get("cookie", "")
            verified = b'"code":"1234"' in request.content
            return httpx.Response(200, json={"d": verified}, headers={"Set-Cookie": "approved=yes; Path=/"} if verified else {})
        if not verified:
            return httpx.Response(200, text=challenge, headers={"Set-Cookie": "challenge=abc; Path=/"})
        assert "approved=yes" in request.headers.get("cookie", "")
        return httpx.Response(200, text=MONTHLY)

    def create(repo: HistoricalDataRepository) -> codal_access.CodalAccess:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return codal_access.CodalAccess(CodalHistoricalProvider(client, repo), (client,))

    monkeypatch.setattr(codal_access, "_create", create)
    with TestClient(app) as api:
        data = api.get("/api/company-reports", params={"symbol": "TEST", "sync": True}).json()
        assert data["assistance"]["status"] == "WAITING_FOR_USER"
        token = data["assistance"]["session_id"]
        payload = {"symbol": "TEST", "session_id": token}
        count = len(calls)
        repo = HistoricalDataRepository()
        assert HistoricalDataSyncManager(repo).sync_company("TEST")["reused_local"]
        assert len(calls) == count  # Analyses must not repeat requests while waiting for the user.
        assert api.post("/api/codal-assistance/image", json=payload).json()["image"].startswith("data:image/png")
        assert api.post("/api/codal-assistance/verify", json=dict(payload, code="wrong")).json() == {"verified": False}
        assert repo.monthly_sales("TEST") == []
        response = api.post("/api/codal-assistance/verify", json=dict(payload, code="1234"))
        assert response.status_code == 200
        result = response.json()
        assert result["verified"] and result["reports"]["sync"]["status"] == "SUCCESS"
        assert len(result["reports"]["monthly_sales"]) == 1
        count = len(calls)
        assert HistoricalDataSyncManager(HistoricalDataRepository()).sync_company("TEST")["reused_local"]
        assert len(calls) == count
        # Even explicit update only discovers metadata; the saved report is not downloaded again.
        api.get("/api/company-reports", params={"symbol": "TEST", "sync": True})
        assert all(path.endswith("/q") for method, path in calls[count:])
        assert api.post("/api/codal-assistance/verify", json=dict(payload, code="1234")).status_code == 409
        assert len(HistoricalDataRepository().monthly_sales("TEST")) == 1
        assert "1234" not in str(repo.state("TEST", "KODAL_COMPANY"))


def test_failed_amendment_is_retried_even_after_metadata_was_saved(tmp_path) -> None:
    repo = HistoricalDataRepository(tmp_path / "amendment.db")
    stage = 0
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "search.codal.ir":
            letter = monthly_letter()
            if stage:
                letter["Title"] += " (اصلاحیه)"
            return httpx.Response(200, json={"Letters": [letter] if request.url.params["Category"] == "3" else [], "TotalPages": 1})
        if stage == 1:
            return httpx.Response(503)
        return httpx.Response(200, text=MONTHLY.replace("100</td>", "120</td>") if stage == 2 else MONTHLY)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = CodalHistoricalProvider(client, repo)
        provider.sync_company("TEST")
        stage = 1
        assert provider.sync_company("TEST", force=True)["pending_changed"] == ["monthly"]
        stage = 2
        result = provider.sync_company("TEST", force=True)
        assert result["status"] == "SUCCESS" and result["pending_changed"] == []
    assert repo.monthly_sales("TEST")[0]["sales_value"]["value"] == 120_000_000


def test_restart_requests_fresh_session_without_losing_stored_data(tmp_path) -> None:
    from smart.codal_access import assistance_info
    repo = HistoricalDataRepository(tmp_path / "restart.db")
    repo.save_monthly(parse_monthly(monthly_letter(), MONTHLY, "TEST", "https://www.codal.ir/Reports/monthly"), MONTHLY)
    repo.record_sync("TEST", "KODAL_COMPANY", {"action_required": "CODAL_USER_VERIFICATION", "status": "PARTIAL"})
    assert assistance_info(HistoricalDataRepository(repo.path), "TEST")["status"] == "SESSION_EXPIRED"
    assert len(HistoricalDataRepository(repo.path).monthly_sales("TEST")) == 1
