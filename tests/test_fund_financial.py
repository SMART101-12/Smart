from smart.conditional_levels import conditional_levels
from smart.fund_financial import (fund_asset_link, fund_financial_evidence,
                                  is_fund_instrument, parse_fund_asset_sheet,
                                  zero_nav_observation)


def test_fund_sheet_requires_explicit_period_unit_and_official_url():
    base = "https://www.codal.ir/Reports/Decision.aspx?LetterSerial=abc"
    index = '<select id="ddlTable"><option value="19">نظر حسابرس</option><option value="15">صورت خالص دارایی ها</option></select>'
    link = fund_asset_link(index, base)
    assert link.endswith("sheetId=15")
    assert fund_asset_link(index, "https://codal.ir.evil.test/Reports/a") is None
    raw = '<p>میلیون ریال</p><table><tr><th>شرح</th><th>1404/12/29</th><th>1403/12/30</th></tr>' \
          '<tr><td>جمع دارایی ها</td><td>120</td><td>999</td></tr>' \
          '<tr><td>خالص ارزش هر واحد (ریال)</td><td>10,000</td><td>9,000</td></tr></table>'
    cells = parse_fund_asset_sheet(raw, "1404/12/29", link, "doc-1")
    assert cells["total_assets"]["value"] == 120
    assert cells["nav_per_unit"]["value"] == 10000
    assert cells["nav_per_unit"]["unit"] == "IRR/unit"
    assert cells["nav_per_unit"]["source_url"] == link
    ambiguous = raw.replace('<th>1403/12/30</th>', '<th>1404/12/29</th>')
    assert parse_fund_asset_sheet(ambiguous, "1404/12/29", link, "doc-1") == {}
    zero_nav = raw.replace('>10,000</td>', '>0</td>')
    assert "nav_per_unit" not in parse_fund_asset_sheet(zero_nav, "1404/12/29", link, "doc-1")
    assert zero_nav_observation(zero_nav, "1404/12/29", link, "doc-1")["status"] == "UNUSABLE_ZERO"
    net_assets = raw.replace('خالص ارزش هر واحد (ریال)', 'خالص دارایی ها')
    assert parse_fund_asset_sheet(net_assets, "1404/12/29", link, "doc-1")["net_assets"]["value"] == 10000


def test_fund_evidence_does_not_use_equity_score():
    class Repo:
        def reports(self, symbol):
            return [{"report_type": "annual", "months": 12, "period": "1404/12/29",
                     "audited": True, "document_id": "doc-1", "source_date": "1405/03/04",
                     "source_url": "https://www.codal.ir/Reports/doc-1",
                     "metrics": {"net_profit": {"value": 100, "unit": "million_IRR",
                                                "locator": "table:1/row:4/column:1"}}}]

        def asset(self, *args):
            return None

        def state(self, *args):
            return {"status": "PARTIAL"}

    assert is_fund_instrument({"lVal30": "صندوق پالایشی یکم"})
    result = fund_financial_evidence(Repo(), "پالایش", fetch_missing=False)
    assert result["instrument_type"] == "FUND"
    assert result["financial_score"] is None
    assert result["annual"][0]["metrics"]["net_profit"]["document_id"] == "doc-1"
    assert "verified_nav_per_unit" in result["missing_data"]


def test_rejected_unconfirmed_range_does_not_get_invented_levels():
    rows = [{"date": f"202601{i:02d}", "open": 100, "high": 102,
             "low": 98, "close": 100, "volume": 1000} for i in range(1, 26)]
    result = conditional_levels(rows, "TEST", model_decision="REJECT")
    assert result["status"] == "no_setup"
    assert result["signal_status"] == "NO_SETUP"
    assert result["conditional"] is None


def test_zero_ohlc_suspended_rows_are_excluded_without_filling():
    rows = [{"date": f"202601{i:02d}", "open": 100, "high": 102,
             "low": 98, "close": 100, "volume": 1000} for i in range(1, 26)]
    rows[4].update(open=0, high=0, low=0)
    result = conditional_levels(rows, "TEST", model_decision="REJECT")
    assert result["excluded_invalid_bars"] == 1
    assert result["signal_status"] == "NO_SETUP"
    assert result["conditional"] is None
    assert result["evidence"]["resistance"] == 102
