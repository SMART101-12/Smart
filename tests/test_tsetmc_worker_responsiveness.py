import asyncio
from threading import Event

from smart import tsetmc


def test_market_computation_does_not_block_status_polling(monkeypatch):
    started, release = Event(), Event()

    async def source(*args, **kwargs):
        return {}

    async def search(symbol):
        return {"insCode": "123"}

    def compute(*args):
        started.set()
        assert release.wait(5), "event loop could not poll while market computation ran"
        return {"symbol": "TEST"}

    monkeypatch.setattr(tsetmc, "search_symbol", search)
    monkeypatch.setattr(tsetmc, "_register_history_identity", lambda *_: None)
    for name in ("instrument_info", "closing_info", "daily_history", "client_type"):
        monkeypatch.setattr(tsetmc, name, source)
    monkeypatch.setattr(tsetmc, "_complete_market_analysis", compute)

    async def run():
        task = asyncio.create_task(tsetmc.analyze_symbol("TEST"))
        try:
            while not started.is_set():
                await asyncio.sleep(.001)
            release.set()
            assert await task == {"symbol": "TEST"}
        finally:
            release.set()
            if not task.done():
                task.cancel()

    asyncio.run(asyncio.wait_for(run(), 5))
