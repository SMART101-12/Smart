from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from smart_v2.analysis.service import AnalysisService
from smart_v2.analysis.trade_plan import EntryExitEngine
from smart_v2.analysis.output_formatter import AnalysisOutputFormatter


def bars() -> list[dict]:
    rows = [{"date": str(date(2026, 1, 1) + timedelta(days=i)), "open": 99.,
             "high": 101., "low": 98., "close": 100., "volume": 100.} for i in range(22)]
    rows[-1].update(open=101., high=103., low=100., close=102., volume=160.)
    return rows


def test_breakout_requires_structure_atr_and_volume() -> None:
    engine = EntryExitEngine()
    result = engine.generate(bars(), "TEST")
    assert result.status == "ready" and result.plan
    p = result.plan
    assert p.sl < p.entry_zone[0] <= p.entry_zone[1] < p.tp1 < p.tp2
    assert (p.tp1 - p.entry_zone[1]) / (p.entry_zone[1] - p.sl) == pytest.approx(2)
    assert result == engine.generate(list(reversed(bars())), "TEST")
    rows = bars()
    rows[-1]["volume"] = 100
    assert engine.generate(rows, "TEST").status == "no_setup"
    rows = bars()
    rows[-1].update(open=99, close=100, high=101, low=98)
    assert engine.generate(rows, "TEST").status == "no_setup"


def test_retest_and_invalidation() -> None:
    rows = bars()
    rows[-2].update(open=101, low=100, high=104, close=103, volume=160)
    rows[-1].update(open=101, low=101, high=103, close=102, volume=140)
    result = EntryExitEngine().generate(rows, "TEST")
    assert result.status == "ready"
    assert result.evidence["setup"] == "retest"


@pytest.mark.parametrize("change", ["missing", "nan", "duplicate", "ohlc", "boolean"])
def test_invalid_data_never_produces_plan(change: str) -> None:
    rows = bars()
    if change == "missing": rows[-1].pop("volume")
    if change == "nan": rows[-1]["close"] = float("nan")
    if change == "duplicate": rows[-1]["date"] = rows[0]["date"]
    if change == "ohlc": rows[-1]["low"] = 500
    if change == "boolean": rows[-1]["volume"] = True
    result = EntryExitEngine().generate(rows, "TEST")
    assert result.status == "insufficient_data" and result.plan is None


def test_service_formatter_and_api() -> None:
    from smart.webapp import app
    service = AnalysisService()
    assert service.trade_plan([], "TEST")["status"] == "insufficient_data"
    assert service.trade_plan(bars(), "TEST", "1h")["status"] == "insufficient_data"
    report = service.report([], symbol="TEST")
    assert report["status"] == "insufficient_data" and report["trade_plan"] is None
    assert AnalysisOutputFormatter().format({})["schema_version"] == "smart-report-v1"
    response = TestClient(app).post('/api/trade-plan', json={"symbol": "TEST", "records": bars()})
    assert response.status_code == 200 and response.json()["status"] == "ready"
