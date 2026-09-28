from fastapi.testclient import TestClient

from smart import webapp


def test_chart_filters_excluded_and_invalid_bars_without_rounding(monkeypatch):
    summary = {"quality_gate": {"latest_valid_date": "2026-09-27",
                               "invalid_ohlc_dates": ["2026-09-25"],
                               "incomplete_session_dates": ["2026-09-28"]}}
    def row(day, close=100.75):
        return {"date": day, "open": 100.25, "high": 102.5,
                "low": 99.25, "close": close, "volume": 1200.5}
    raw = {"history": [row("20260928"), row("20260927"), row("20260925"),
                       row("20260924", 500), row("20260923"), row("20260927")]}
    monkeypatch.setattr(webapp, "_read_unified_artifact",
                        lambda symbol, analysis_id, name: summary if name == "analysis.json" else raw)
    response = TestClient(webapp.app).get("/api/analysis/TEST/abc/chart")
    assert response.status_code == 200
    bars = response.json()["bars"]
    assert [bar["source_date"] for bar in bars] == ["2026-09-23", "2026-09-27"]
    assert bars[-1]["close"] == 100.75
    assert bars[-1]["volume"] == 1200.5


def test_dashboard_assets_and_missing_chart():
    client = TestClient(webapp.app)
    assert client.get("/dashboard.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/dashboard.css").headers["content-type"].startswith("text/css")
    assert client.get("/api/analysis/TEST/" + "0" * 32 + "/chart").status_code == 404
