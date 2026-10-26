import base64
import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from smart import ai, webapp
from smart.analysis_contract import build_structured_analysis, validate_structured_analysis
from smart.analysis_explanation import render_explanation, fingerprint
from smart.analysis_horizons import horizon_summaries
from smart.analyst_evidence import SourceCapture, _capture, capture_response, repository_evidence
from smart.financial_history import HistoricalDataRepository


def reference():
    return {"symbol": "TEST", "analysis_id": "a" * 32, "as_of": "2026-10-25",
            "decision": {"state": "WAIT"}, "momentum": {"rsi": 58, "macd": 2},
            "quality_gate": {"status": "DEGRADED", "blockers": ["source_stale_or_unavailable"]},
            "missing_data": ["verified_fundamentals"], "entry_exit": {"plan": None}}


def fake_model(monkeypatch, output):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(output))
    monkeypatch.setattr(ai, "get_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    return calls


def test_explanation_round_trip_through_installed_responses_sdk(monkeypatch):
    import httpx
    from openai import OpenAI
    requests = []
    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/responses"
        assert payload["text"]["format"]["strict"] is True
        assert set(payload["text"]["format"]["schema"]["properties"]) == {"fact_ids"}
        return httpx.Response(200, json={
            "id": "resp_verified_test", "object": "response", "created_at": 0,
            "status": "completed", "model": "gpt-5", "output": [{
                "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": '{"fact_ids":["momentum"]}', "annotations": []}]}]})
    with OpenAI(api_key="test-only", base_url="https://sdk-test.invalid/v1",
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        monkeypatch.setattr(ai, "get_client", lambda: client)
        result = ai.ask_structured_analysis(reference())
    assert len(requests) == 1
    assert result["reference"] == reference()
    assert "58" in result["answer"]


def test_model_selects_facts_without_changing_numeric_reference(monkeypatch):
    original = reference()
    frozen = deepcopy(original)
    calls = fake_model(monkeypatch, {"fact_ids": ["momentum"]})
    result = ai.ask_structured_analysis(original, question="RSI?")
    assert result["reference"] == original == frozen
    assert result["reference_sha256"] == fingerprint(frozen)
    assert "58" in result["answer"]
    assert "WAIT" in result["answer"]  # required caveats/conclusion cannot be omitted
    assert "source_stale_or_unavailable" in result["answer"]
    assert len(calls) == 1
    assert "snapshot" not in json.loads(calls[0]["input"])


@pytest.mark.parametrize("output", [
    {"fact_ids": ["momentum"], "momentum": {"rsi": 99}},
    {"fact_ids": ["BUY NOW 999"]}, {"fact_ids": ["momentum", "momentum"]},
    {"fact_ids": []}, {"fact_ids": "momentum"}, {"answer": "RSI=99"},
])
def test_valid_json_cannot_override_prices_indicators_or_conclusion(monkeypatch, output):
    fake_model(monkeypatch, output)
    with pytest.raises(RuntimeError):
        ai.ask_structured_analysis(reference())


def test_chat_rejects_tampered_ai_reference_and_preserves_local_answer(monkeypatch):
    original = reference()
    monkeypatch.setattr(webapp, "_read_unified_artifact", lambda *args: deepcopy(original))
    def malicious(snapshot, **kwargs):
        snapshot["momentum"]["rsi"] = 99
        return {"reference": snapshot, "fact_ids": ["momentum"], "answer": "RSI=99"}
    monkeypatch.setattr(webapp, "ask_structured_analysis", malicious)
    response = TestClient(webapp.app).post("/api/chat", json={
        "symbol": "TEST", "analysis_id": "a" * 32, "structured": True})
    assert response.status_code == 200
    assert response.json()["structured_analysis"]["momentum"]["rsi"] == 58
    assert "99" not in response.json()["answer"]
    assert response.json()["structured_analysis_ai_error"]


def test_chat_never_displays_ai_authored_text(monkeypatch):
    original = reference()
    monkeypatch.setattr(webapp, "_read_unified_artifact", lambda *args: deepcopy(original))
    monkeypatch.setattr(webapp, "ask_structured_analysis", lambda snapshot, **kwargs: {
        "reference": snapshot, "fact_ids": ["momentum"], "answer": "BUY 999 RSI 99"})
    response = TestClient(webapp.app).post("/api/chat", json={
        "symbol": "TEST", "analysis_id": "a" * 32, "structured": True})
    assert response.status_code == 200
    assert "999" not in response.json()["answer"]
    assert "58" in response.json()["answer"]


def test_new_chat_runs_the_unified_job_and_never_an_independent_scan(monkeypatch):
    from smart import unified_analysis as ua
    original = reference()
    calls = []
    monkeypatch.setattr(ua, "create_job", lambda symbol: {"analysis_id": "a" * 32, "symbol": symbol})
    async def run(job):
        calls.append(job["analysis_id"])
        job["status"] = "PARTIAL"
    async def forbidden(*args, **kwargs):
        raise AssertionError("Independent scanner must not run for chat")
    monkeypatch.setattr(ua, "run_job", run)
    monkeypatch.setattr(webapp, "live_initial_analysis", forbidden)
    monkeypatch.setattr(webapp, "historical_exam", forbidden)
    monkeypatch.setattr(webapp, "_read_unified_artifact", lambda *args: deepcopy(original))
    result = TestClient(webapp.app).post("/api/chat", json={"symbol": "TEST", "include_exam": True})
    assert result.status_code == 200
    assert calls == ["a" * 32]
    assert result.json()["structured_analysis"] == original


def test_narrative_keeps_both_source_failures_and_data_defects():
    original = reference()
    original["data_quality"] = {"issues": ["conflicting_duplicate_dates"]}
    original["quality_gate"]["acquisition"] = {"status": "PARTIAL",
        "rejected": [{"date": "2026-10-25", "error": "Closing price outside observed high/low"}],
        "unresolved_dates": ["2026-10-25"]}
    result = render_explanation(original, ["decision"])
    assert "source_stale_or_unavailable" in result["answer"]
    assert "conflicting_duplicate_dates" in result["answer"]
    assert "Closing price outside observed high/low" in result["answer"]


def test_unified_narrative_includes_the_verified_indicator_contract():
    original = reference()
    original["legacy_technical"] = {"schema_version": "analysis-contract-v2",
                                    "momentum": {"rsi": 47.125, "macd": -2, "macd_signal": -1},
                                    "support_resistance": {"supports": [98], "resistances": [125]}}
    original.pop("momentum")
    result = render_explanation(original)
    assert "47.125" in result["answer"]
    assert "98" in result["answer"]
    assert "125" in result["answer"]


def test_unavailable_prediction_confidence_is_not_a_quality_probability():
    result = build_structured_analysis({"symbol": "EMPTY"})
    assert result["final_assessment"]["confidence_0_100"] is None
    assert result["final_assessment"]["score_0_100"] is None
    assert result["data_quality"]["score_0_100"] <= 35
    result["final_assessment"]["confidence_0_100"] = 95
    assert "invalid:uncalibrated_predictive_confidence" in validate_structured_analysis(result)


def test_horizons_use_full_history_and_expose_short_windows():
    start = date(2026, 1, 1)
    rows = [{"source_date": (start + timedelta(days=i)).isoformat(),
             "low": 90 + i, "high": 110 + i, "close": 100 + i} for i in range(150)]
    result = horizon_summaries(rows)
    assert result["120"]["observations"] == 120
    assert result["120"]["from_date"] == rows[30]["source_date"]
    assert result["250"]["status"] == "INSUFFICIENT_DATA"
    assert result["250"]["low"] == 90
    assert result["20"]["high"] == 259


def test_raw_capture_keeps_rejected_body_and_freezes_completed_evidence(tmp_path):
    collector = SourceCapture(tmp_path)
    token = _capture.set(collector)
    try:
        body = b'{"closingPriceDaily": [{"pClosing": -1}]}'
        capture_response("https://cdn.tsetmc.com/api/test", body, status=200)
        records = collector.freeze()["responses"]
        capture_response("https://cdn.tsetmc.com/api/late", b"late")
        assert len(collector.records) == 1
        assert base64.b64decode(records[0]["body_base64"]) == body
        assert records[0]["sha256"] == hashlib.sha256(body).hexdigest()
        assert [json.loads(line) for line in collector.path.read_text(encoding="utf-8").splitlines()] == records
    finally:
        _capture.reset(token)


def test_export_copies_binary_source_and_scopes_to_requested_symbol(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "evidence.db")
    repo.save_asset("TEST", "123", "https://codal.ir/report.pdf", b"original bytes", "application/pdf")
    repo.save_asset("OTHER", "456", "https://codal.ir/other.pdf", b"other bytes", "application/pdf")
    result = repository_evidence(repo, "TEST", "123")
    assert len(result["codal_assets"]) == 1
    assert base64.b64decode(result["codal_assets"][0]["payload"]["value"]) == b"original bytes"


def test_source_failure_is_captured_before_http_or_json_validation(monkeypatch, tmp_path):
    import httpx
    from smart import tsetmc
    body = b"upstream returned a broken page, not JSON"
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            return httpx.Response(502, content=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(tsetmc.httpx, "AsyncClient", Client)
    collector = SourceCapture(tmp_path)
    token = _capture.set(collector)
    try:
        with pytest.raises(tsetmc.TSETMCError):
            asyncio.run(tsetmc._get("/test"))
        assert collector.records[0]["status"] == 502
        assert base64.b64decode(collector.records[0]["body_base64"]) == body
    finally:
        _capture.reset(token)
