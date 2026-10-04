import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from smart.financial_history import HistoricalDataRepository
from smart.market_history import repository_history


def _row(day, volume):
    return {"dEven": int(day.strftime("%Y%m%d")), "pClosing": 100, "priceFirst": 100,
            "priceMax": 101, "priceMin": 99, "qTotTran5J": volume}


def test_previous_intraday_bar_is_refreshed_once_even_when_cache_is_recent(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "db.sqlite")
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    prior = today - timedelta(days=1)
    stamp = datetime.combine(prior, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tehran")) + timedelta(hours=11)
    repo.save_daily_history_incremental("123", "tsetmc", stamp, [_row(prior, 50), _row(today, 10)])
    repo.record_sync("123", "TSETMC", {"status": "SUCCESS"})
    calls = []
    async def get(path):
        calls.append(path)
        assert path.endswith(prior.strftime("%Y%m%d"))
        return {"closingPriceDaily": _row(prior, 100)}
    first = asyncio.run(repository_history("123", get, repository=repo))
    assert next(r for r in first if r["dEven"] == int(prior.strftime("%Y%m%d")))["qTotTran5J"] == 100
    assert asyncio.run(repository_history("123", get, repository=repo)) == first
    assert len(calls) == 1


def test_older_symbol_alias_cannot_overwrite_newer_instrument_snapshot(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "db.sqlite")
    now = datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo("Asia/Tehran")).date() - timedelta(days=2)
    repo.register_instrument("ALIAS", "123")
    repo.save_daily_history_incremental("ALIAS", "tsetmc", now - timedelta(hours=1), [_row(day, 50)])
    repo.save_daily_history_incremental("123", "tsetmc", now, [_row(day, 100)])
    repo.record_sync("123", "TSETMC", {"status": "SUCCESS"})
    async def forbidden(path):
        raise AssertionError("Current snapshot should be reused")
    result = asyncio.run(repository_history("123", forbidden, repository=repo))
    assert result[0]["qTotTran5J"] == 100
