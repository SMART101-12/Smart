import asyncio
import json
from contextvars import ContextVar
from threading import Event

import pytest

from smart.analysis_workers import (
    AnalysisWorkerPool, WorkerCapacityError, cancellation_checkpoint,
)


def test_cancelled_blocking_call_keeps_capacity_until_real_completion():
    pool = AnalysisWorkerPool(1)
    started, release, finished = Event(), Event(), Event()

    def block():
        started.set()
        release.wait(5)
        finished.set()

    async def run():
        task = asyncio.create_task(pool.run(block))
        while not started.is_set():
            await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(WorkerCapacityError):
            await pool.run(lambda: "must not start")
        release.set()
        while not finished.is_set():
            await asyncio.sleep(.001)
        # The post-call cancellation check and done callback release the slot.
        for _ in range(1000):
            try:
                assert await pool.run(lambda: "next") == "next"
                break
            except WorkerCapacityError:
                await asyncio.sleep(.001)
        else:
            pytest.fail("worker slot was leaked")

    try:
        asyncio.run(asyncio.wait_for(run(), 5))
    finally:
        release.set()
        pool.shutdown()


def test_cooperative_work_stops_after_cancellation_and_context_is_copied():
    pool = AnalysisWorkerPool(1)
    started, finished = Event(), Event()
    request_context = ContextVar("fixture", default="missing")
    observed = []

    def compute():
        observed.append(request_context.get())
        started.set()
        try:
            while True:
                cancellation_checkpoint()
        finally:
            finished.set()

    async def run():
        request_context.set("request-a")
        task = asyncio.create_task(pool.run(compute))
        while not started.is_set():
            await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        while not finished.is_set():
            await asyncio.sleep(.001)
        assert observed == ["request-a"]

    try:
        asyncio.run(asyncio.wait_for(run(), 5))
    finally:
        pool.shutdown()


def test_worker_exception_releases_capacity():
    pool = AnalysisWorkerPool(1)

    def fail():
        raise ValueError("fixture")

    async def run():
        with pytest.raises(ValueError, match="fixture"):
            await pool.run(fail)
        assert await pool.run(lambda: 42) == 42

    try:
        asyncio.run(run())
    finally:
        pool.shutdown()


def test_stage_timeout_never_publishes_late_research(monkeypatch, tmp_path):
    from smart.analysis_stages import StageRunner
    from smart import research_cache
    from smart.research_cache import cached_research

    pool = AnalysisWorkerPool(1)
    started, release = Event(), Event()
    monkeypatch.setenv("SMART_RESEARCH_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(research_cache, "implementation_fingerprint", lambda: "fixture")
    job = {"symbol": "TEST", "warnings": [], "stages": []}
    stage = StageRunner(job, tmp_path, .05)

    def compute():
        started.set()
        release.wait(5)
        return {"status": "COMPLETE", "score": 99}

    async def research():
        return await cached_research("historical_exam", {}, lambda: pool.run(compute))

    async def run():
        assert await stage("historical_exam", research) is None
        assert started.is_set()
        assert job["stages"][0]["status"] == "NOT_AVAILABLE"
        saved = (tmp_path / "job.json").read_bytes()
        release.set()
        # Wait for the underlying worker, not just cancellation of its awaiter.
        for _ in range(1000):
            try:
                await pool.run(lambda: None)
                break
            except WorkerCapacityError:
                await asyncio.sleep(.001)
        else:
            pytest.fail("late worker did not finish")
        assert not list((tmp_path / "cache").rglob("*.json"))
        assert (tmp_path / "job.json").read_bytes() == saved
        log = json.loads((tmp_path / "analysis.log").read_text(encoding="utf-8"))
        assert log["status"] == "NOT_AVAILABLE"
        assert "budget exceeded" in log["error"]

    try:
        asyncio.run(asyncio.wait_for(run(), 5))
    finally:
        release.set()
        pool.shutdown()
