from fastapi.testclient import TestClient

from smart import webapp


def test_dashboard_and_strategy_catalog_endpoints():
    client = TestClient(webapp.app)
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    response = client.get("/api/strategies")
    assert response.status_code == 200
    assert response.json()["count"] == 200
    assert client.get("/api/learning/UNKNOWN").status_code == 200


def test_chat_endpoint_uses_structured_payload(monkeypatch):
    async def fake_scan(symbols):
        return {"status": "ok", "results": [{"symbol": symbols[0]}], "errors": []}

    async def fake_exam(symbol):
        return {
            "status": "COMPLETE",
            "symbol": symbol,
            "protocol": {"decision_uses_future_fields": False},
            "strategy_count": 200,
            "metrics": {},
            "segments": [],
            "leaderboard": [],
        }

    monkeypatch.setattr(webapp, "live_initial_analysis", fake_scan)
    monkeypatch.setattr(webapp, "historical_exam", fake_exam)
    seen = {}

    def fake_model(prompt):
        seen["prompt"] = prompt
        return "توضیح آزمایشی"

    monkeypatch.setattr(webapp, "ask_model", fake_model)
    client = TestClient(webapp.app)
    response = client.post(
        "/api/chat",
        json={"symbol": "TEST", "question": "چه نتیجه‌ای؟", "include_exam": True},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "توضیح آزمایشی"
    assert "future_return_5d" not in seen["prompt"]
