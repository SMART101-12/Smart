import json
from datetime import date, timedelta

from smart.analysis_contract import (
    ANALYSIS_SCHEMA_VERSION,
    analysis_json_schema,
    build_structured_analysis,
    validate_structured_analysis,
)


def _snapshot(rows=25):
    start = date(2026, 1, 1)
    history = []
    for index in range(rows):
        close = 100 + index
        history.append(
            {
                "date": (start + timedelta(days=index)).strftime("%Y%m%d"),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + index,
                "rsi14": 58,
                "macd": 2,
                "macd_signal": 1,
                "sma20": close - 4,
                "sma50": close - 8,
                "ema12": close - 3,
                "ema26": close - 5,
                "atr14": 2,
                "volume_ratio20": 1.4,
            }
        )
    return {
        "symbol": "TEST",
        "price": 124,
        "retail_net_volume": "12.5",
        "smart_money": {"phase": "accumulation"},
        "analysis": {
            "as_of": history[-1]["date"],
            "factor_engine": {"composite": 72, "decision": "BUY"},
            "technical_history": {"history": history, "latest": history[-1]},
        },
    }


def test_contract_is_valid_and_excludes_future_labels():
    payload = build_structured_analysis(_snapshot(), previous_outcomes=[{"result": "win"}])

    assert payload["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert payload["trend"]["long_term"] == "bullish"
    assert payload["volume_flow"]["real_money_flow"] == 12.5
    assert payload["provenance"]["future_rows_used_for_current_signal"] is False
    assert payload["provenance"]["previous_outcomes_count"] == 1
    assert "future_return_5d" not in json.dumps(payload)
    assert validate_structured_analysis(payload) == []


def test_contract_fails_closed_for_missing_history():
    payload = build_structured_analysis({"symbol": "EMPTY"})

    assert payload["data_quality"]["status"] == "poor"
    assert payload["final_assessment"]["label"] == "watchlist"
    assert payload["final_assessment"]["confidence_0_100"] <= 35
    assert validate_structured_analysis(payload) == []


def test_schema_contains_fixed_provenance_constraints():
    schema = analysis_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["provenance"]["properties"]["point_in_time"]["enum"] == [True]
    assert schema["properties"]["provenance"]["properties"]["future_rows_used_for_current_signal"]["enum"] == [False]
