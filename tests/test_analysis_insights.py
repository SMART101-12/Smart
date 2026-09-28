from fastapi.testclient import TestClient

from smart.analysis_insights import explain_gates, report_source_health
from smart import unified_analysis as ua, webapp


def test_gate_explanations_preserve_recorded_decision_and_volume_precision():
    summary = {"decision": {"version": "DECISION-1.1", "gates": {"data_quality": False,
                "volume_confirmation": False, "approved_model_version": False}},
               "quality_gate": {"status": "DEGRADED", "current_window": {"status": "MEDIUM"}},
               "flow": {"price_volume_proxy": {"volume_ratio_20": .40213}}}
    gates = {g["key"]: g for g in explain_gates(summary)}
    assert gates["data_quality"]["observed"]["status"] == "DEGRADED"
    assert gates["volume_confirmation"]["observed"]["percent_of_20_session_mean"] == .40213 * 100
    assert gates["approved_model_version"]["passed"] is False
    assert all(g["required"] and g["next_step"] for g in gates.values())


def test_successful_codal_download_does_not_mark_missing_nav_as_available():
    sources = report_source_health({"instrument_type": "FUND",
                  "fundamental_quality_gate": {"source_status": "SUCCESS"}})
    assert next(s for s in sources if s["source"] == "کدال")["status"] == "SUCCESS"
    assert next(s for s in sources if s["source"] == "NAV صندوق")["status"] == "UNAVAILABLE"


def test_history_is_read_only_and_matches_persian_symbol_alias(monkeypatch, tmp_path):
    monkeypatch.setattr(ua, "_root", lambda: tmp_path)
    job = ua.create_job("عيار")
    client = TestClient(webapp.app)
    result = client.get("/api/analysis/عیار/history").json()
    assert result["items"][0]["analysis_id"] == job["analysis_id"]
    assert len(list(tmp_path.glob("*/*/job.json"))) == 1
    assert client.get("/api/analysis/عیار/history?limit=1000").status_code == 422
