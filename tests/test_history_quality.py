from datetime import date

from smart.history_quality import audit_symbol, compare_symbols


START = date(2026, 8, 1)
END = date(2026, 8, 16)


def test_calendar_classifies_weekly_and_official_closures():
    result = audit_symbol("فولاد", start=START, end=END)
    assert result["status"] == "OK"
    assert result["weekly_closed_excluded"] == 4  # 6, 7, 13, 14 Aug
    assert result["official_closed_excluded"] >= 2  # 4 and 12 Aug are official closures
    assert "2026-08-04" not in result["missing_expected"]
    assert "2026-08-12" not in result["missing_expected"]


def test_zero_trade_records_are_not_called_missing():
    result = audit_symbol("فولاد", start=START, end=END)
    assert "2026-08-05" not in result["zero_trade_records"]
    assert result["classification"]["DATA_PRESENT"] == 10


def test_palesh_and_foolad_are_compared_on_same_expected_calendar():
    result = compare_symbols(["پالایش", "فولاد"], start=START, end=END)
    assert result["expected_trading_dates"] == 10
    assert result["symbols"]["فولاد"]["missing"] == []
    assert result["symbols"]["پالایش"]["missing"] == ["2026-08-16"]
    assert result["common_present"] == 9
