"""Synthetic fixtures exercise integrity; they are NOT real Codal financial data."""
import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from smart.codal import CodalHistoricalProvider, HistoricalDataSyncManager, parse_document
from smart.financial_history import HistoricalDataRepository, METRICS
from smart.financial_scoring import FinancialScoringEngine, integrate_financial_score
from smart.market_history import repository_history


def fixture_report(year=1404, revision=False, audited=True, missing=None, months=12,
                   basis="standalone", revenue=None):
    """Explicitly artificial test evidence, never loaded into the runtime database."""
    period = f"{year}/12/29"
    title = f"صورت های مالی دوره {months} ماهه منتهی به {period} (حسابرسی {'شده' if audited else 'نشده'})"
    if revision:
        title += " اصلاحیه"
    if basis == "consolidated":
        title += " تلفیقی"
    values = {m: 10 for m in METRICS}
    values.update(revenue=revenue if revenue is not None else 100 + (year - 1400) * 20,
                  assets=200, liabilities=80, equity=120, net_profit=30,
                  operating_profit=40, operating_cash_flow=35, eps=3,
                  nonoperating_profit=2, finance_cost=3)
    if missing:
        values[missing] = None
    raw = '<p>SYNTHETIC TEST FIXTURE — میلیون ریال</p><table><tr><th>شرح</th><th>' + period + '</th></tr>'
    raw += ''.join(f'<tr><td>{label}</td><td>{values[m] if values[m] is not None else "-"}</td></tr>'
                   for m, label in METRICS.items())
    raw += '</table>'
    letter = {"Symbol": "TEST", "Title": title,
              "TracingNo": f"fixture-{year}-{revision}-{audited}-{months}-{basis}",
              "PublishDateTime": f"{year + 1}/03/{'20' if revision else '01'} 10:00:00"}
    report = parse_document(letter, raw, "TEST", "https://www.codal.ir/Reports/fixture")
    return report, raw


@pytest.fixture
def repo(tmp_path):
    return HistoricalDataRepository(tmp_path / "stocks.db")


def seed(repo, missing=None, years=range(1400, 1405)):
    for year in years:
        repo.save_report(*fixture_report(year, missing=missing))


def test_five_year_calculated_score_and_traceable_ratios(repo):
    seed(repo)
    result = FinancialScoringEngine(repo).analyze("TEST")
    assert result["coverage"] == {"available": 5, "required": 5}
    assert 0 <= result["financial_score"] <= 100
    roe = result["annual"][0]["cells"]["roe"]
    assert roe["value"] == .25
    assert roe["badge"] == "CALCULATED FROM VERIFIED DATA"
    assert len(roe["source_reference"]) == 2


def test_missing_is_null_and_never_scored_as_zero(repo):
    seed(repo, missing="revenue")
    result = FinancialScoringEngine(repo).analyze("TEST")
    assert result["financial_score"] is None
    assert all(r["cells"]["revenue"]["value"] is None for r in result["annual"])
    assert all(r["cells"]["net_margin"]["value"] is None for r in result["annual"])
    assert "موجود نیست" in result["persian_analysis"]["facts"][0]["text"]


def test_empty_does_not_fabricate_score_or_financial_years(repo):
    result = FinancialScoringEngine(repo).analyze("NEW")
    assert result["financial_score"] is None
    assert result["annual"] == []
    assert result["data_quality_score"] == 0
    assert integrate_financial_score(71, result)["score"] == 71


def test_dedup_restart_and_new_symbol(repo):
    report, raw = fixture_report()
    assert repo.save_report(report, raw) == "inserted"
    assert repo.save_report(report, raw) == "skipped"
    reopened = HistoricalDataRepository(repo.path)
    assert len(reopened.reports("TEST")) == 1
    assert reopened.reports("NEW") == []


def test_revision_history_and_audited_precedence(repo):
    repo.save_report(*fixture_report())
    repo.save_report(*fixture_report(revision=True, revenue=200))
    repo.save_report(*fixture_report(revision=True, audited=False, revenue=900))
    assert len(repo.reports("TEST", selected=False)) == 3
    assert repo.reports("TEST")[0]["metrics"]["revenue"]["value"] == 200


def test_interim_and_consolidated_are_separate(repo):
    repo.save_report(*fixture_report(months=3))
    repo.save_report(*fixture_report(basis="consolidated"))
    assert FinancialScoringEngine(repo).analyze("TEST")["coverage"]["available"] == 0
    assert FinancialScoringEngine(repo).analyze("TEST", "consolidated")["coverage"]["available"] == 1


def test_injected_ai_number_is_rejected_against_raw_evidence(repo):
    report, raw = fixture_report()
    report["metrics"]["revenue"]["value"] = 123456789
    with pytest.raises(ValueError, match="evidence mismatch"):
        repo.save_report(report, raw)
    assert repo.reports("TEST") == []


@pytest.mark.parametrize("change", ["source", "url", "nan", "period", "unit"])
def test_invalid_source_schema_values_are_rejected(repo, change):
    report, raw = fixture_report()
    if change == "source": report["source"] = "AI"
    if change == "url": report["source_url"] = "https://codal.ir.evil.test/report"
    if change == "nan": report["metrics"]["eps"]["value"] = float("nan")
    if change == "period": report["period"] = "1404/13/99"
    if change == "unit": report["metrics"]["eps"]["unit"] = "USD"
    with pytest.raises(ValueError): repo.save_report(report, raw)


def test_missing_year_is_not_bridged(repo):
    seed(repo, years=[1399, 1400, 1402, 1403, 1404])
    result = FinancialScoringEngine(repo).analyze("TEST")
    assert result["financial_score"] is None
    assert result["annual"][1]["year"] == 1401
    assert result["annual"][1]["cells"]["revenue"]["value"] is None


class Provider:
    def __init__(self, reports): self.reports, self.calls = reports, []
    def fetch(self, symbol, known_ids, publication_cursor, years):
        self.calls.append((known_ids, publication_cursor))
        return {"reports": [r for r in self.reports if r[0]["document_id"] not in known_ids],
                "cursor": "1405/03/20 10:00:00", "rejected": []}


def test_incremental_sync_and_publication_cursor_discovers_old_revision(repo):
    provider = Provider([fixture_report(y) for y in range(1400, 1405)])
    sync = HistoricalDataSyncManager(repo, provider)
    assert sync.sync_financial("TEST")["inserted"] == 5
    assert sync.sync_financial("TEST")["reused_local"]
    assert len(provider.calls) == 1
    provider.reports.append(fixture_report(1402, revision=True))
    result = sync.sync_financial("TEST", force=True)
    assert result["updated"] == 1
    assert len(provider.calls[-1][0]) == 5
    assert provider.calls[-1][1] == "1405/03/20 10:00:00"
    assert len(repo.reports("TEST", selected=False)) == 6


def test_source_down_uses_local_and_preserves_last_success(repo):
    provider = Provider([fixture_report(y) for y in range(1400, 1405)])
    manager = HistoricalDataSyncManager(repo, provider)
    success = manager.sync_financial("TEST")
    def down(*args): raise httpx.ConnectError("source down")
    provider.fetch = down
    failed = manager.sync_financial("TEST", force=True)
    assert failed["last_sync_date"] == success["last_sync_date"]
    result = FinancialScoringEngine(repo).analyze("TEST")
    assert result["financial_score"] is not None
    assert result["warnings"]
    assert len(repo.audit("TEST")) == 2


def test_parser_rejects_ambiguous_column_and_preserves_comparatives():
    report, raw = fixture_report()
    letter = {"Symbol": "TEST", "Title": report["source_title"], "TracingNo": "test",
              "PublishDateTime": report["source_date"]}
    bad = raw.replace('<th>1404/12/29</th>', '<th>1404/12/29</th><th>1404/12/29</th>')
    with pytest.raises(ValueError, match="Unsupported"):
        parse_document(letter, bad, "TEST", report["source_url"])
    with pytest.raises(ValueError, match="symbol mismatch"):
        parse_document(letter, raw, "OTHER", report["source_url"])


def test_provider_only_downloads_unknown_documents():
    report, raw = fixture_report()
    letter = {"Symbol": "TEST", "Title": report["source_title"], "TracingNo": report["document_id"],
              "PublishDateTime": report["source_date"], "Url": "/Reports/fixture"}
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"Letters": [letter], "TotalPages": 1}) if request.url.host == "search.codal.ir" else httpx.Response(200, text=raw)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = CodalHistoricalProvider(client)
        assert len(provider.fetch("TEST", set())["reports"]) == 1
        calls.clear()
        assert provider.fetch("TEST", {report["document_id"]})["reports"] == []
        assert len(calls) == 1


def test_market_persistence_incremental_and_financial_separation(repo):
    yesterday = date.today() - timedelta(days=1)
    row = {"dEven": int(yesterday.strftime("%Y%m%d")), "pClosing": 100, "qTotTran5J": None}
    calls = []
    async def fetch(path):
        calls.append(path)
        if "DailyList" in path: return {"closingPriceDaily": [row, row]}
        return {"closingPriceDaily": dict(row, dEven=int(date.today().strftime("%Y%m%d")))}
    rows = asyncio.run(repository_history("123", fetch, repository=repo))
    assert len(rows) == 1 and rows[0]["qTotTran5J"] is None
    assert len(asyncio.run(repository_history("123", fetch, repository=repo))) == 1
    assert len(calls) == 1
    asyncio.run(repository_history("123", fetch, repository=repo, force=True))
    assert sum("DailyList" in call for call in calls) == 1
    repo.save_report(*fixture_report())
    assert len(repo.reports("TEST")) == 1
    with repo._connect() as con:
        assert con.execute("SELECT count(*) FROM market_history").fetchone()[0] >= 1
        assert con.execute("SELECT count(*) FROM financial_documents").fetchone()[0] == 1


def test_market_source_failure_reuses_local(repo):
    row = {"dEven": 20260815, "pClosing": 100}
    repo.save_daily_history("123", "tsetmc", datetime.now(timezone.utc), [row])
    async def down(path): raise httpx.ConnectError("down")
    rows = asyncio.run(repository_history("123", down, repository=repo, force=True))
    assert rows == [row]
    assert repo.state("123", "TSETMC")["status"] == "PARTIAL"


def test_web_financial_api_and_asset_are_read_only(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from smart.webapp import app
    monkeypatch.setenv("SMART_HISTORICAL_DB", str(tmp_path / "api.db"))
    with TestClient(app) as client:
        data = client.get('/api/financial-history?symbol=TEST&sync=false').json()
        assert data['financial_score'] is None
        assert client.post('/api/financial-history', json={'revenue': 999}).status_code == 405
        assert client.get('/financial-history.js').status_code == 200
        assert client.get('/api/financial-history/audit?symbol=TEST').json()['versions'] == []


def test_old_symbol_keyed_market_rows_are_reused(repo):
    day = date.today()
    row = {"dEven": int(day.strftime("%Y%m%d")), "pClosing": 100}
    repo.save_daily_history("TEST", "tsetmc", datetime.now(timezone.utc), [row])
    repo.register_instrument("TEST", "123")
    async def forbidden(path):
        pytest.fail("Existing symbol history must not trigger a full refetch")
    assert asyncio.run(repository_history("123", forbidden, repository=repo)) == [row]


def test_codal_partial_pagination_preserves_downloaded_evidence(repo):
    report, raw = fixture_report()
    letter = {"Symbol": "TEST", "Title": report["source_title"],
              "TracingNo": report["document_id"], "PublishDateTime": report["source_date"],
              "Url": "/Reports/fixture"}
    pages = []
    def handler(request):
        if request.url.host != "search.codal.ir":
            return httpx.Response(200, text=raw)
        page = int(request.url.params["PageNumber"])
        pages.append(page)
        if page == 2:
            raise httpx.ReadTimeout("second page interrupted")
        return httpx.Response(200, json={"Letters": [letter], "Page": page})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sync = HistoricalDataSyncManager(repo, CodalHistoricalProvider(client))
        result = sync.sync_financial("TEST")
    assert pages == [1, 2, 2, 2]
    assert result["status"] == "PARTIAL"
    assert result["inserted"] == 1
    assert result["cursor"] is None
    assert len(repo.reports("TEST")) == 1


def test_codal_repeated_page_cannot_claim_success():
    report, raw = fixture_report()
    letter = {"Symbol": "TEST", "Title": report["source_title"],
              "TracingNo": report["document_id"], "PublishDateTime": report["source_date"],
              "Url": "/Reports/fixture"}
    def handler(request):
        return (httpx.Response(200, json={"Letters": [letter], "Page": 1})
                if request.url.host == "search.codal.ir" else httpx.Response(200, text=raw))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CodalHistoricalProvider(client).fetch("TEST", set())
    assert len(result["reports"]) == 1
    assert "Repeated" in result["rejected"][0]["error"]


def test_legacy_market_calculations_do_not_fill_missing_values():
    from smart.tsetmc import _analyze_rows
    from smart.strategy_lab import bars_from_rows
    from smart_v2.analysis.stock_service import StockAnalysisService
    result = _analyze_rows("TEST", {}, {}, [], {})
    for metric in ("price", "change_pct", "volume_ratio", "retail_buy_power", "money_flow_score"):
        assert result[metric] is None
    assert result["smart_money"]["score"] is None
    assert result["technical"]["score"] is None
    rows = [{"dEven": 20260815, "pClosing": 100}]
    with pytest.raises(ValueError, match="Insufficient verified"):
        bars_from_rows(rows)
    with pytest.raises(ValueError, match="Insufficient verified"):
        StockAnalysisService.to_frame(rows)
