from datetime import date, timedelta

import pytest

from smart.data_quality_gate import (calculated, financial_gate, market_gate, publication_date,
                                     observed, source_date_cutoff)


def bars(count=50):
    start = date(2026, 9, 27) - timedelta(days=count - 1)
    return [{"date": (start + timedelta(days=i)).isoformat(), "open": 100,
             "high": 103, "low": 98, "close": 101, "volume": 1000}
            for i in range(count)]


def test_quality_gate_audits_nontrading_duplicates_without_filling():
    rows = bars()
    rows[10] = {**rows[10], "open": 0, "high": 0, "low": 0, "volume": 0}
    rows.append(dict(rows[5]))
    result = market_gate(rows, symbol="TEST", as_of=date(2026, 9, 27))
    assert result["status"] == "DEGRADED"
    assert result["valid_ohlcv_rows"] == 49
    assert result["latest_bar_verified"] is True
    assert result["invalid_ohlc_dates"] == [rows[10]["date"]]
    assert result["duplicate_dates"] == [rows[5]["date"]]
    assert result["corporate_action_adjustment"] == "UNVERIFIED"
    assert result["blockers"] == []
    assert rows[10]["open"] == 0


def test_invalid_latest_future_or_stale_source_blocks_current_conclusion():
    invalid = bars()
    invalid[-1] = {**invalid[-1], "high": 0}
    assert "latest_bar_invalid_or_future" in market_gate(
        invalid, symbol="TEST", as_of=date(2026, 9, 27))["blockers"]
    future = bars() + [{**bars()[-1], "date": "2026-09-28"}]
    assert "future_dated_source_rows" in market_gate(
        future, symbol="TEST", as_of=date(2026, 9, 27))["blockers"]
    stale = market_gate(bars(), symbol="TEST", as_of=date(2026, 10, 10))
    assert stale["freshness"] == "STALE"
    assert "source_stale_or_unavailable" in stale["blockers"]


def test_incomplete_current_session_is_excluded_without_replacing_last_complete_bar():
    result = market_gate(bars(), symbol="TEST", as_of=date(2026, 9, 27),
                         completed_before=date(2026, 9, 27))
    assert result["incomplete_session_dates"] == ["2026-09-27"]
    assert result["latest_raw_source_date"] == "2026-09-27"
    assert result["latest_valid_date"] == "2026-09-26"
    assert result["latest_bar_verified"] is True


def test_provenance_distinguishes_observed_and_calculated_values():
    raw = observed(100, unit="IRR", source="TSETMC", source_date="2026-09-27")
    metric = calculated(10, unit="percent", formula="net_assets/price", inputs=[raw])
    assert raw["calculated"] is False and metric["calculated"] is True
    assert metric["source_dates"] == ["2026-09-27"]
    with pytest.raises(ValueError, match="dated inputs"):
        calculated(5, unit="IRR", formula="guess", inputs=[])
    assert source_date_cutoff("2026-09-27", as_of=date(2026, 9, 27))
    assert not source_date_cutoff("2026-09-28", as_of=date(2026, 9, 27))
    assert source_date_cutoff("1405/06/20", as_of=date(2026, 9, 27))
    assert not source_date_cutoff("1405/07/06", as_of=date(2026, 9, 27))
    assert publication_date("1405/07/05 12:00:00") == date(2026, 9, 27)
    assert publication_date("۱۴۰۵/۰۷/۰۵") == date(2026, 9, 27)
    assert publication_date("1405/12/30") is None


def test_codal_rate_limit_and_future_publication_are_visible():
    report = {"report_type": "annual", "period": "1404/12/29", "audited": True,
              "document_id": "verified-1", "source_date": "1405/06/20"}
    sync = {"status": "PARTIAL", "rejected": [{"error": "HTTP 429"}]}
    partial = financial_gate([report], sync, instrument_type="FUND",
                             as_of=date(2026, 9, 27))
    assert partial["source_status"] == "RATE_LIMITED"
    assert partial["point_in_time"] is True
    assert "codal_source_partial" in partial["blockers"]
    future = financial_gate([{**report, "source_date": "2026-09-28"}],
                            {"status": "SUCCESS"}, instrument_type="EQUITY",
                            as_of=date(2026, 9, 27))
    assert future["status"] == "INVALID"
    assert future["future_document_ids"] == ["verified-1"]
