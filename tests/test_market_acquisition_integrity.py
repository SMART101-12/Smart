import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from smart.archive import deduplicate_rows
from smart.data_quality_gate import market_gate
from smart.financial_history import HistoricalDataRepository
from smart.market_history import repository_history, validate_market_row


def row(day, **changes):
    value = {"dEven": int(day.strftime("%Y%m%d")), "pClosing": 100, "pDrCotVal": 100,
             "priceFirst": 100, "priceMax": 102, "priceMin": 98, "qTotTran5J": 1000}
    value.update(changes)
    return value


@pytest.mark.parametrize("changes", [{"pDrCotVal": 120}, {"priceFirst": 97}])
def test_provider_rejects_price_outside_received_range(changes):
    with pytest.raises(ValueError, match="outside observed high/low"):
        validate_market_row(row(date(2026, 1, 1), **changes))


def test_conflicting_versions_are_not_arbitrarily_used_as_verified_data():
    day = date(2026, 9, 27)
    rows = [row(day - timedelta(days=i)) for i in range(30)]
    rows += [row(day, pClosing=101)]
    original = [dict(item) for item in rows]
    canonical, audit = deduplicate_rows(rows)
    assert len(canonical) == 30
    assert audit["conflicting_duplicate_dates"] == [day.isoformat()]
    gate = market_gate(rows, symbol="TEST", as_of=day)
    assert gate["latest_bar_verified"] is False
    assert gate["valid_ohlcv_rows"] == 29
    assert "latest_bar_invalid_or_future" in gate["blockers"]
    assert day.isoformat() in gate["current_window"]["invalid_dates"]
    assert gate["price_range_validation"]["status"] == "UNAVAILABLE"
    assert rows == original


def test_identical_duplicates_are_audited_without_inventing_a_conflict():
    day = date(2026, 9, 27)
    rows = [row(day - timedelta(days=i)) for i in range(30)]
    rows.append({**rows[0], "provider_note": "same observed prices"})
    gate = market_gate(rows, symbol="TEST", as_of=day)
    assert gate["conflicting_duplicate_dates"] == []
    assert gate["latest_bar_verified"] is True
    assert gate["price_range_validation"]["observed_close"] == 100


def test_rejected_latest_record_is_visible_and_retried_despite_recent_cache(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "market.db")
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    valid_day, bad_day = today - timedelta(days=2), today - timedelta(days=1)
    calls = []
    async def get(path):
        calls.append(path)
        if "DailyList" in path:
            return {"closingPriceDaily": [row(valid_day), row(bad_day, pDrCotVal=120)]}
        requested = datetime.strptime(path.rsplit("/", 1)[1], "%Y%m%d").date()
        return {"closingPriceDaily": row(requested)}
    received = asyncio.run(repository_history("123", get, repository=repo))
    state = repo.state("123", "TSETMC")
    assert state["status"] == "PARTIAL"
    gate = market_gate(received, symbol="TEST", as_of=today, acquisition=state,
                       completed_before=today)
    assert "latest_source_observation_rejected" in gate["blockers"]
    assert gate["acquisition"]["rejected"][0]["date"] == int(bad_day.strftime("%Y%m%d"))
    received = asyncio.run(repository_history("123", get, repository=repo))
    assert any(path.endswith(bad_day.strftime("%Y%m%d")) for path in calls[1:])
    assert any(item["dEven"] == int(bad_day.strftime("%Y%m%d")) for item in received)
    assert repo.state("123", "TSETMC")["status"] == "SUCCESS"
    before = len(calls)
    asyncio.run(repository_history("123", get, repository=repo))
    assert len(calls) == before


def test_unresolved_source_dates_are_not_assumed_to_be_holidays():
    today = date(2026, 9, 27)
    rows = [row(today - timedelta(days=i)) for i in range(30)]
    gate = market_gate(rows, symbol="TEST", as_of=today, acquisition={
        "status": "PARTIAL", "unresolved_dates": ["2026-09-26"],
        "rejected": [{"date": "2026-09-26", "error": "Source row missing"}]})
    assert "unresolved_completed_source_dates" in gate["blockers"]
    assert gate["acquisition"]["unresolved_completed_dates"] == ["2026-09-26"]
    assert gate["price_range_validation"]["exchange_daily_limits"] == "NOT_CHECKED"


def test_distinct_settlement_and_traded_close_are_preserved_without_false_rejection():
    # Recorded TSETMC field values: final trade was inside the traded range,
    # while the source's separate settlement was outside that range.
    day = date(2025, 9, 20)
    observed = row(day, pClosing=67350, pDrCotVal=67400,
                   priceFirst=67400, priceMax=67400, priceMin=67400)
    assert validate_market_row(observed)["pClosing"] == 67350
    gate = market_gate([observed], symbol="TEST", as_of=day)
    assert gate["invalid_ohlc_dates"] == []
    assert gate["latest_bar_verified"] is True
    assert gate["price_range_validation"]["observed_close"] == 67400
    assert gate["price_range_validation"]["observed_settlement"] == 67350
    assert gate["price_range_validation"]["close_basis"] == "last_trade"
    canonical, _ = deduplicate_rows([observed], price_basis="last_trade")
    assert canonical[0]["close"] == canonical[0]["low"] == canonical[0]["high"] == 67400
    assert canonical[0]["settlement_price"] == 67350
    assert observed["pClosing"] == 67350


def test_saved_canonical_candle_keeps_its_original_price_basis():
    raw = row(date(2025, 9, 20), pClosing=100, pDrCotVal=101)
    saved, _ = deduplicate_rows([raw])
    assert saved[0]["close"] == 100
    restored, _ = deduplicate_rows(saved, price_basis="last_trade")
    assert restored[0]["close"] == 100
    assert restored[0]["close_basis"] == "settlement"


def test_conflicting_provider_duplicates_never_overwrite_repository_evidence(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "market.db")
    day = date(2026, 9, 27)
    async def get(path):
        return {"closingPriceDaily": [row(day), row(day, pDrCotVal=101)]}
    received = asyncio.run(repository_history("123", get, repository=repo))
    assert received == []
    assert repo.history("123", "tsetmc") == []
    state = repo.state("123", "TSETMC")
    assert state["status"] == "PARTIAL"
    assert state["conflicting_duplicate_dates"] == [20260927]
    gate = market_gate(received, symbol="TEST", as_of=day, acquisition=state)
    assert "latest_source_observation_rejected" in gate["blockers"]
