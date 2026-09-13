from fastapi.testclient import TestClient
from datetime import datetime, timezone

from smart import webapp


def test_dashboard_and_strategy_catalog_endpoints():
    client = TestClient(webapp.app)
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    response = client.get("/api/strategies")
    assert response.status_code == 200
    assert response.json()["count"] == 200
    assert client.get("/api/learning/UNKNOWN").status_code == 200


def test_status_and_risk_endpoints():
    client = TestClient(webapp.app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["service"] == "SMART"
    response = client.post(
        "/api/risk/position-size",
        json={"account_equity": 100000, "risk_percent": 1, "entry": 100, "stop": 90},
    )
    assert response.status_code == 200
    assert response.json()["result"]["risk_budget"] == 1000
    portfolio = client.post(
        "/api/portfolio/summary",
        json={"positions": [{"symbol": "AAA", "quantity": 2, "entry": 10, "current": 12}]},
    )
    assert portfolio.status_code == 200
    assert portfolio.json()["portfolio"]["unrealized_pnl"] == 4


def test_daily_run_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_DAILY_DB", str(tmp_path / "reports.sqlite3"))

    as_of = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")

    async def fake_scan(symbols):
        return {
            "status": "ok", "results": [{
                "symbol": symbols[0],
                "structured_analysis": {
                    "as_of": as_of, "data_quality": {"status": "good", "issues": []},
                    "final_assessment": {"score_0_100": 60},
                },
                "analysis": {"technical_history": {"latest": {"date": as_of, "close": 10}}},
            }], "errors": [],
        }

    monkeypatch.setattr(webapp, "live_initial_analysis", fake_scan)
    client = TestClient(webapp.app)
    created = client.post("/api/daily-runs", json={"symbols": ["AAA"], "symbol_timeout_seconds": 2})
    assert created.status_code == 202
    run_id = created.json()["run"]["run_id"]
    detail = client.get(f"/api/daily-runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run"]["status"] == "completed"
    assert client.get("/api/daily-runs").json()["runs"][0]["run_id"] == run_id


def test_structured_analysis_endpoint_is_local_and_parseable(monkeypatch):
    async def fake_scan(symbols):
        return {
            "status": "ok",
            "source": "TEST",
            "results": [{"symbol": symbols[0], "structured_analysis": {
                "schema_version": "analysis-contract-v1",
                "symbol": symbols[0],
                "as_of": None,
                "data_quality": {"status": "poor", "issues": ["no_ohlcv_rows"]},
                "trend": {"short_term": "unknown", "mid_term": "unknown", "long_term": "unknown"},
                "momentum": {"rsi": None, "macd": None, "macd_signal": None, "interpretation": "insufficient data"},
                "volume_flow": {"volume_status": "unknown", "real_money_flow": None, "smart_money_hint": None},
                "market_phase": "unknown",
                "support_resistance": {"supports": [], "resistances": []},
                "risk": {"level": "very_high", "reasons": ["poor_data_quality"]},
                "scenarios": [
                    {"name": "bullish", "condition": "n/a", "outlook": "n/a"},
                    {"name": "bearish", "condition": "n/a", "outlook": "n/a"},
                    {"name": "neutral", "condition": "n/a", "outlook": "n/a"},
                ],
                "final_assessment": {"score_0_100": 50, "confidence_0_100": 35, "label": "watchlist", "summary": "insufficient data"},
                "actionable_notes": [],
                "warning": ["no_ohlcv_rows"],
                "provenance": {"point_in_time": True, "future_rows_used_for_current_signal": False, "previous_outcomes_count": 0},
            }}],
            "errors": [],
        }

    monkeypatch.setattr(webapp, "live_initial_analysis", fake_scan)
    response = TestClient(webapp.app).get("/api/analysis?symbol=TEST")

    assert response.status_code == 200
    assert response.json()["analysis"]["symbol"] == "TEST"
    assert response.json()["analysis"]["provenance"]["future_rows_used_for_current_signal"] is False


def test_symbol_profiles_endpoint_uses_per_symbol_training(monkeypatch):
    async def fake_profiles(symbols, **kwargs):
        assert symbols == ["فولاد", "فملی"]
        assert kwargs["years"] == 10
        return {
            "status": "ok",
            "stage": "per_symbol_adaptive_entry_training",
            "symbols_requested": symbols,
            "results": [{"symbol": "فولاد", "status": "COMPLETE"}],
            "errors": [],
        }

    monkeypatch.setattr(webapp, "focus_symbol_profiles", fake_profiles)
    client = TestClient(webapp.app)
    response = client.get("/api/symbol-profiles?symbols=%D9%81%D9%88%D9%84%D8%A7%D8%AF,%D9%81%D9%85%D9%84%DB%8C")

    assert response.status_code == 200
    assert response.json()["results"][0]["symbol"] == "فولاد"


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
