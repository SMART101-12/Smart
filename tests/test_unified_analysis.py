import json
import asyncio
import math
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smart import tsetmc, webapp
from smart import unified_analysis as ua
from smart.codal import HistoricalDataSyncManager
from smart import strategy_lab
from smart.unified_evaluation import evaluate_profile
from smart.symbol_learning import _settle_trade, _trades_in_range
from smart.technical_analysis import Bar
from smart import symbol_learning


def test_windows_job_polling_lock_retries_atomic_write(monkeypatch, tmp_path):
    target = tmp_path / "job.json"
    target.write_text("{}", encoding="utf-8")
    original = Path.replace
    calls = []
    def briefly_locked(path, destination):
        calls.append(destination)
        if len(calls) == 1:
            raise PermissionError("a status reader still has job.json open")
        return original(path, destination)
    monkeypatch.setattr(Path, "replace", briefly_locked)
    ua._write(target, {"status": "COMPLETED"})
    assert len(calls) == 2
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "COMPLETED"


def test_unified_partial_job_and_integrity(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_ANALYSIS_ROOT", str(tmp_path))

    async def search(symbol):
        return {"insCode": "123", "lVal18AFC": symbol}

    async def market(symbol):
        return {"structured_analysis": {"as_of": "20260926",
                "data_quality": {"status": "good", "issues": []},
                "risk": {"level": "medium"},
                "final_assessment": {"confidence_0_100": 40}},
                "smart_money": {"score": None}}

    async def history(code):
        return []

    monkeypatch.setattr(tsetmc, "search_symbol", search)
    monkeypatch.setattr(tsetmc, "analyze_symbol", market)
    monkeypatch.setattr(tsetmc, "daily_history", history)
    monkeypatch.setattr(HistoricalDataSyncManager, "sync_financial",
                        lambda self, symbol: {"status": "SOURCE_UNAVAILABLE"})
    monkeypatch.setattr(ua, "_root", lambda: tmp_path)
    job = ua.create_job("TEST")
    asyncio.run(ua.run_job(job))
    assert job["status"] == "PARTIAL"
    assert ua.find_job(job["analysis_id"])["status"] == "PARTIAL"
    assert "historical_exam_metrics" not in ua.get_artifact("TEST", job["analysis_id"], "analysis.json")["missing_data"]
    assert ua.get_artifact("TEST", job["analysis_id"], "chatgpt.json")["status"] == "PARTIAL"
    assert ua.get_artifact("TEST", job["analysis_id"], "analysis.json")["confidence"] is None
    assert len(ua.get_artifact("TEST", job["analysis_id"], "analysis.json")["market_models"]["models"]) == 10
    assert (tmp_path / "TEST" / job["analysis_id"] / "analysis.log").exists()
    client = TestClient(webapp.app)
    assert client.get(f"/api/analyze/{job['analysis_id']}").json()["status"] == "PARTIAL"
    assert client.get(f"/api/analysis/TEST/{job['analysis_id']}/chatgpt").status_code == 200
    assert client.get(f"/api/analysis/TEST/{job['analysis_id']}/model-card").status_code == 200
    path = tmp_path / "TEST" / job["analysis_id"] / "analysis.json"
    path.write_text(json.dumps({"status": "COMPLETED"}), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        ua.get_artifact("TEST", job["analysis_id"], "analysis.json")


def test_unified_routes_and_simple_dashboard(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_ANALYSIS_ROOT", str(tmp_path))
    client = TestClient(webapp.app)
    homepage = client.get("/").text
    assert homepage.count('<button id="analyze">') == 1
    assert 'id="market-models"' in homepage
    assert client.get("/legacy").status_code == 200
    assert client.post("/api/analyze", json={"symbol": "../bad"}).status_code == 422
    assert client.get("/api/analyze/invalid").status_code == 404


def test_exam_uses_recent_history_instead_of_first_decisions(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_ANALYSIS_ROOT", str(tmp_path))
    seen = {}

    async def search(symbol):
        return {"insCode": "123", "lVal30": "صندوق نمونه"}

    async def market(symbol):
        return {"structured_analysis": {"data_quality": {"status": "good"}}}

    async def history(code):
        start = date(2024, 1, 1)
        return [{"date": (start + timedelta(days=i)).strftime("%Y%m%d"),
                 "open": 100, "high": 101, "low": 99, "close": 100,
                 "volume": 1000} for i in range(350)]

    def exam(rows, **kwargs):
        seen["dates"] = [row["date"] for row in rows]
        return {"status": "COMPLETE"}

    monkeypatch.setattr(tsetmc, "search_symbol", search)
    monkeypatch.setattr(tsetmc, "analyze_symbol", market)
    monkeypatch.setattr(tsetmc, "daily_history", history)
    monkeypatch.setattr(strategy_lab, "walk_forward_exam", exam)
    monkeypatch.setattr(HistoricalDataSyncManager, "sync_financial",
                        lambda self, symbol: {"status": "SOURCE_UNAVAILABLE"})
    job = ua.create_job("TEST")
    asyncio.run(ua.run_job(job))
    assert len(seen["dates"]) == 300
    assert seen["dates"][-1] == (date(2024, 1, 1) + timedelta(days=349)).strftime("%Y%m%d")
    result = ua.get_artifact("TEST", job["analysis_id"], "analysis.json")
    assert result["instrument_type"] == "FUND"
    assert result["fundamental"]["equity_score_applicable"] is False
    assert "verified_fund_nav_per_unit" in result["missing_data"]
    assert "verified_five_year_fundamentals" not in result["missing_data"]
    assert result["entry_exit"]["conditional"] is None
    assert "source_stale_or_unavailable" in result["quality_gate"]["blockers"]
    assert len(result["market_models"]["models"]) == 10


def test_frozen_oos_rejection_preserves_validation_choice():
    rows = [{"date": (date(2024, 1, 1) + timedelta(days=i)).strftime("%Y%m%d"),
             "open": 100, "high": 101, "low": 99, "close": 100 + i,
             "volume": 1000} for i in range(80)]
    selection = {"config": {"config_id": "chosen-on-validation"},
                 "range_metrics": {"validation": {"trades": 6, "cumulative_return_pct": 3},
                                   "test": {"trades": 6, "cumulative_return_pct": -4}},
                 "validation_gate": {"passed": True}, "test_gate": {"passed": False}}
    profile = {"status": "COMPLETE", "selected_model": selection,
               "protocol": {"transaction_cost_pct_round_trip": .35,
                            "candidate_selection": "validation_only",
                            "frozen_test_used_for_candidate_selection": False,
                            "no_lookahead": True, "entry_time": "next_open"},
               "ranges": {"validation": {"start_index": 48, "stop_index": 64},
                          "test": {"start_index": 64, "stop_index": 79}},
               "coverage": {"first_date": rows[0]["date"], "last_date": rows[-1]["date"],
                            "bars_used": len(rows)},
               "analysis_path": {"entries_and_outcomes": [{}] * 12}}
    result = evaluate_profile(profile, rows)
    assert result["self_test"]["decision"] == "REJECT"
    assert result["backtest"]["selected_config"] == selection["config"]
    assert result["self_test"]["checks"]["validation_only_selection"] is True


def test_cached_history_keeps_technical_when_live_snapshot_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_ANALYSIS_ROOT", str(tmp_path))

    async def search(symbol):
        return {"insCode": "123"}

    async def market(symbol):
        raise RuntimeError("live closing snapshot unavailable")

    async def history(code):
        start = date(2024, 1, 1)
        return [{"date": (start + timedelta(days=i)).strftime("%Y%m%d"),
                 "open": 100+i, "high": 102+i, "low": 99+i,
                 "close": 101+i, "volume": 1000} for i in range(70)]

    monkeypatch.setattr(tsetmc, "search_symbol", search)
    monkeypatch.setattr(tsetmc, "analyze_symbol", market)
    monkeypatch.setattr(tsetmc, "daily_history", history)
    monkeypatch.setattr(strategy_lab, "walk_forward_exam", lambda rows, **kw: {"status": "COMPLETE"})
    monkeypatch.setattr(symbol_learning, "build_symbol_profile",
                        lambda rows, **kw: {"status": "INSUFFICIENT_HISTORY"})
    monkeypatch.setattr(HistoricalDataSyncManager, "sync_financial",
                        lambda self, symbol: {"status": "SOURCE_UNAVAILABLE"})
    job = ua.create_job("TEST")
    asyncio.run(ua.run_job(job))
    result = ua.get_artifact("TEST", job["analysis_id"], "analysis.json")
    assert result["technical"] is not None
    assert result["provenance"]["market"] == "TSETMC cached history"
    assert "live_market_snapshot" in result["missing_data"]
    assert result["confidence"] is None


def test_gap_through_stop_uses_actual_open():
    bars = [Bar("20260101", 100, 102, 98, 100, 1000, None, None),
            Bar("20260102", 100, 101, 99, 100, 1000, None, None),
            Bar("20260103", 78, 85, 75, 80, 1000, None, None)]
    trade = _settle_trade({"entry_index": 1, "entry_price": 100,
                           "stop_price": 90, "target_price": 110,
                           "planned_exit_index": 3}, bars, 2, .0035)
    assert trade["exit_reason"] == "gap_through_stop"
    assert trade["exit_price"] == 80
    assert trade["net_return_pct"] == -20.35


def test_validation_does_not_score_outcome_revealed_in_frozen_test():
    trades = [{"decision_index": 68, "exit_index": 69, "net_return_pct": 2},
              {"decision_index": 69, "exit_index": 72, "net_return_pct": 80}]
    assert _trades_in_range(trades, 50, 70) == trades[:1]


def test_frozen_test_prices_cannot_change_validation_selected_model():
    start = date(2023, 1, 1)
    rows = []
    for i in range(360):
        price = 100 + i * .12 + 4 * math.sin(i / 9)
        rows.append({"date": (start + timedelta(days=i)).strftime("%Y%m%d"),
                     "open": price, "high": price * 1.02,
                     "low": price * .98, "close": price,
                     "volume": 1000 + i % 13})
    original = symbol_learning.build_symbol_profile(rows, symbol="TEST", persist=False)
    altered = [dict(row) for row in rows]
    boundary = original["ranges"]["test"]["start_index"]
    for row in altered[boundary:]:
        for key in ("open", "high", "low", "close"):
            row[key] *= 3
    changed = symbol_learning.build_symbol_profile(altered, symbol="TEST", persist=False)
    assert changed["selected_model"]["config"] == original["selected_model"]["config"]
    assert changed["selected_model"]["range_metrics"]["validation"] == original["selected_model"]["range_metrics"]["validation"]
