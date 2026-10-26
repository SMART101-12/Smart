"""Bound blocking work for analysis jobs, including work outliving its awaiter.

Cancellation is cooperative. A blocking library call retains its slot until it
actually returns; cancelling an awaiter never creates another free worker slot.
"""
from __future__ import annotations

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event
from typing import Any, Callable


class WorkerCapacityError(RuntimeError):
    """No worker slot is available; do not build an unbounded pending queue."""


class WorkCancelled(RuntimeError):
    """A computation reached a cancellation checkpoint."""


_stop: contextvars.ContextVar[Event | None] = contextvars.ContextVar("analysis_stop", default=None)


def cancellation_checkpoint() -> None:
    stop = _stop.get()
    if stop is not None and stop.is_set():
        raise WorkCancelled("Analysis computation cancelled")


class AnalysisWorkerPool:
    def __init__(self, capacity: int = 4) -> None:
        self._slots = BoundedSemaphore(capacity)
        self._executor = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix="smart-analysis")

    async def run(self, function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        if not self._slots.acquire(blocking=False):
            raise WorkerCapacityError("Analysis worker capacity reached; retry after running work finishes")
        stop = Event()
        context = contextvars.copy_context()

        def execute():
            token = _stop.set(stop)
            try:
                cancellation_checkpoint()
                result = function(*args, **kwargs)
                cancellation_checkpoint()
                return result
            finally:
                _stop.reset(token)

        try:
            future = self._executor.submit(context.run, execute)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())
        wrapped = asyncio.wrap_future(future)
        # A cancelled awaiter will not retrieve a late exception itself.
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.shield(wrapped)
        except asyncio.CancelledError:
            stop.set()
            future.cancel()
            raise

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


_pool = AnalysisWorkerPool()
run_blocking = _pool.run
