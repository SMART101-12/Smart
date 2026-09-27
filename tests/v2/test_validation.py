from smart_v2.validation.runner import validate_symbol_payload


def test_valid_row_passes():
    payload = {
        "requested_symbol": "PALAYESH",
        "ins_code": "67675656072510693",
        "daily_history": [
            {"dEven": "20260815", "pOpen": 100, "pHigh": 110, "pLow": 90, "pClosing": 105, "pDrCotVal": 105, "zTotTran": 10, "qTotTran5J": 1000, "qTotCap": 105000}
        ],
    }
    result = validate_symbol_payload(payload)
    assert result.status == "PASS"
    assert result.checked_records == 1


def test_bad_ohlc_fails():
    payload = {
        "requested_symbol": "PALAYESH",
        "ins_code": "67675656072510693",
        "daily_history": [{"dEven": "20260815", "pHigh": 90, "pLow": 100}],
    }
    result = validate_symbol_payload(payload)
    assert result.status == "FAIL"
    assert any(issue.code == "OHLC_RANGE" for issue in result.issues)


def test_duplicate_date_fails():
    payload = {
        "requested_symbol": "PALAYESH",
        "ins_code": "67675656072510693",
        "daily_history": [{"dEven": "20260815"}, {"dEven": "20260815"}],
    }
    result = validate_symbol_payload(payload)
    assert result.status == "FAIL"
    assert any(issue.code == "DUPLICATE_DATE" for issue in result.issues)
