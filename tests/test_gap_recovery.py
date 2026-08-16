from datetime import date

from smart.gap_recovery import _expected_dates
from smart.market_calendar import EQUITY, GOLD_FUND, expected_dates, market_type


def test_expected_iran_market_week_excludes_thursday_friday():
    dates = list(_expected_dates(date(2026, 8, 13), date(2026, 8, 16)))
    assert dates == [date(2026, 8, 15), date(2026, 8, 16)]


def test_shared_closed_date_is_removed_for_market_type():
    open_dates = {date(2026, 8, 15), date(2026, 8, 16), date(2026, 8, 17)}
    # A shared closure is represented by the calendar layer; this test uses an
    # empty calendar after applying a closed date through the public helper.
    from smart.market_calendar import record_closed_dates

    record_closed_dates(EQUITY, [date(2026, 8, 16)], reason="TEST")
    try:
        result = expected_dates(date(2026, 8, 15), date(2026, 8, 17), open_dates, EQUITY)
        assert date(2026, 8, 16) not in result
    finally:
        # Keep tests isolated by removing the temporary runtime calendar entry.
        import smart.market_calendar as mc
        payload = mc._load()
        payload.get("closed_dates", {}).get(EQUITY, {}).pop("2026-08-16", None)
        mc._save(payload)


def test_market_types():
    assert market_type("عیار") == GOLD_FUND
    assert market_type("پالایش") == EQUITY
