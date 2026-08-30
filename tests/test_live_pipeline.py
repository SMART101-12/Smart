import asyncio

from smart import tsetmc


def test_live_initial_analysis_deduplicates_limits_and_reports_failures(monkeypatch):
    async def fake(symbol):
        if symbol == "BAD":
            raise tsetmc.TSETMCError("unavailable")
        return {
            "symbol": symbol,
            "smart_money": {"score": 80, "phase": "accumulation", "confirmations": [], "warnings": []},
            "technical": {"score": 70},
            "data_quality": 90,
        }

    monkeypatch.setattr(tsetmc, "analyze_symbol", fake)
    result = asyncio.run(tsetmc.live_initial_analysis([" A ", "A", "BAD"]))

    assert result["symbols_requested"] == ["A", "BAD"]
    assert result["status"] == "ok"
    assert [row["rank"] for row in result["results"]] == [1]
    assert result["errors"] == [{"symbol": "BAD", "error": "unavailable"}]


def test_live_initial_analysis_empty_input_is_explicit(monkeypatch):
    result = asyncio.run(tsetmc.live_initial_analysis([]))
    assert result["status"] == "empty"
    assert result["results"] == []
    assert result["errors"] == []


def test_analyze_symbol_includes_downstream_analysis(monkeypatch):
    async def value(_):
        return {}

    async def history(_):
        return [{"dEven": 20260815, "pFirst": 98, "pMax": 105, "pMin": 95,
                 "pClosing": 100, "qTotTran5J": 10}]

    monkeypatch.setattr(tsetmc, "search_symbol", lambda _: value(None))
    monkeypatch.setattr(tsetmc, "instrument_info", lambda _: value(None))
    monkeypatch.setattr(tsetmc, "closing_info", lambda _: value(None))
    monkeypatch.setattr(tsetmc, "daily_history", history)
    monkeypatch.setattr(tsetmc, "client_type", lambda _: value(None))

    class FakeAnalysis:
        def analyze(self, rows, **kwargs):
            assert rows
            return {"status": "ANALYZED", "factor_engine": {"composite": 55}}

    monkeypatch.setattr(tsetmc, "StockAnalysisService", lambda: FakeAnalysis())
    result = asyncio.run(tsetmc.analyze_symbol("X"))
    assert result["analysis"]["status"] == "ANALYZED"
