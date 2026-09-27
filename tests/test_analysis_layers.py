import json

import pytest

from smart.analysis_layers import CONTRACT_VERSION, LAYER_NAMES, from_legacy_summary, layer


def test_layer_contract_is_serializable_and_does_not_promote_bullish_votes():
    summary = {"as_of": "2026-09-27", "instrument_type": "FUND",
               "data_quality": {"status": "medium"},
               "market_models": {"status": "available", "as_of": "2026-09-27",
                                 "models": [{"signal": "bullish"}] * 7},
               "entry_exit": {"signal_status": "NO_SETUP", "reason": "volume weak",
                              "evidence": {"as_of": "20260927"}},
               "self_test": {"decision": "REJECT"},
               "fundamental": {"coverage": {"annual_reports": 5}, "financial_score": None},
               "provenance": {"market": "TSETMC cached history", "fundamental": "KODAL"},
               "warnings": [{"stage": "codal_sync", "error": "HTTP 429"}]}
    result = from_legacy_summary(summary, [
        {"name": "fundamental", "status": "PARTIAL"},
        {"name": "entry_exit", "status": "COMPLETED"},
        {"name": "model_self_test", "status": "COMPLETED"}])
    assert result["contract_version"] == CONTRACT_VERSION
    assert tuple(result["layers"]) == LAYER_NAMES
    assert result["layers"]["technical"]["status"] == "PARTIAL"
    assert result["layers"]["setup"]["evidence"]["status"] == "NO_SETUP"
    assert result["layers"]["decision"]["status"] == "UNAVAILABLE"
    assert result["layers"]["fundamental"]["errors"] == ["HTTP 429"]
    assert result["layers"]["market"]["status"] == "UNAVAILABLE"
    json.dumps(result, ensure_ascii=False, allow_nan=False)


def test_unrecognized_status_and_bad_evidence_are_rejected():
    with pytest.raises(ValueError, match="status"):
        layer(status="BUY", as_of=None)
    with pytest.raises(ValueError, match="mapping"):
        layer(status="SUCCESS", as_of=None, evidence=["unverified"])
