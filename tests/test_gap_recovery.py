from datetime import date

from smart.gap_recovery import _expected_dates


def test_expected_iran_market_week_excludes_thursday_friday():
    dates = list(_expected_dates(date(2026, 8, 13), date(2026, 8, 16)))
    assert dates == [date(2026, 8, 15), date(2026, 8, 16)]
