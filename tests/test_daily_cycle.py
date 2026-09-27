import asyncio
from datetime import datetime, timezone

from smart.daily_cycle import DailyRunStore, execute_daily_run


def _snapshot(symbol: str, as_of: str, score: float = 70, quality: str = "good"):
    return {
        "status": "ok", "results": [{
            "symbol": symbol,
            "structured_analysis": {
                "as_of": as_of,
                "data_quality": {"status": quality, "issues": []},
                "final_assessment": {"score_0_100": score},
            },
            "analysis": {"technical_history": {"latest": {"date": as_of, "close": 100}}},
        }],
        "errors": [],
    }


def test_daily_cycle_checkpoints_and_ranks_only_eligible_rows(tmp_path):
    store = DailyRunStore(tmp_path / "reports.sqlite3")
    report = store.create(["AAA", "BBB"], max_age_days=3)

    as_of = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")

    async def scanner(symbols):
        return _snapshot(symbols[0], as_of, score=80 if symbols[0] == "AAA" else 50,
                         quality="good" if symbols[0] == "AAA" else "medium")

    final = asyncio.run(execute_daily_run(store, report["run_id"], scanner))
    assert final["status"] == "partial"
    assert final["counts"] == {"requested": 2, "received": 2, "eligible": 1, "excluded": 1}
    assert final["top_10"][0]["symbol"] == "AAA"
    assert store.get(report["run_id"])["processed_count"] == 2


def test_daily_cycle_preserves_source_errors(tmp_path):
    store = DailyRunStore(tmp_path / "reports.sqlite3")
    report = store.create(["BAD"])

    async def scanner(_):
        return {"status": "error", "results": [], "errors": [{"error": "offline"}]}

    final = asyncio.run(execute_daily_run(store, report["run_id"], scanner))
    assert final["status"] == "failed"
    assert final["errors"][0]["code"] == "source_error"


def test_daily_cycle_rejects_second_active_run(tmp_path):
    from smart.daily_cycle import ActiveRunError

    store = DailyRunStore(tmp_path / "reports.sqlite3")
    store.create(["AAA"])
    try:
        store.create(["BBB"])
    except ActiveRunError as exc:
        assert exc.run_id
    else:
        raise AssertionError("expected active-run guard")
