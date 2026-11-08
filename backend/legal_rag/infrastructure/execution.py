"""Bounded threads for blocking HTTP workflows; no unbounded submission queue."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import BoundedSemaphore, Lock

from legal_rag.infrastructure.errors import WorkCapacityError, WorkTimeoutError


class BoundedWorkExecutor:
    def __init__(self, *, max_workers: int, timeout_seconds: float):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="legal-rag")
        self._slots = BoundedSemaphore(max_workers)
        self._mutation = Lock()
        self._timeout = timeout_seconds

    async def run[T](self, operation: Callable[[], T], *, exclusive: bool = False) -> T:
        # Do not queue arbitrary work or release slots when only the HTTP waiter ends.
        if not self._slots.acquire(blocking=False):
            raise WorkCapacityError("Service is busy. Retry after current work completes.")
        locked = exclusive and self._mutation.acquire(blocking=False)
        if exclusive and not locked:
            self._slots.release()
            raise WorkCapacityError("A corpus mutation is already running.")

        def release(_):
            if locked:
                self._mutation.release()
            self._slots.release()

        try:
            context = copy_context()
            future = self._pool.submit(context.run, operation)
        except BaseException:
            release(None)
            raise
        future.add_done_callback(release)
        result = asyncio.wrap_future(future)
        # Consume eventual exceptions after a timeout or disconnected caller.
        result.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(result), timeout=self._timeout)
        except TimeoutError as exc:
            raise WorkTimeoutError(
                "Request deadline exceeded; running work retains its capacity."
            ) from exc

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
