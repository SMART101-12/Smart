from datetime import date

from smart_v2.validation.history_quality import _closed_dates


def test_v2_calendar_overrides_include_verified_closures():
    closed = _closed_dates(date(2021, 7, 24), date(2021, 7, 25), "EQUITY")
    closed |= _closed_dates(date(2026, 7, 4), date(2026, 7, 6), "EQUITY")
    assert closed == {
        date(2021, 7, 24), date(2021, 7, 25),
        date(2026, 7, 4), date(2026, 7, 5), date(2026, 7, 6),
    }
