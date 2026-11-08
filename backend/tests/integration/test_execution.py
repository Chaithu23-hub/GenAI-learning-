"""Bounded execution keeps capacity charged until actual work completion."""

import asyncio
from contextvars import ContextVar
from threading import Event

import pytest

from legal_rag.infrastructure import errors, execution


@pytest.mark.asyncio
async def test_request_context_is_preserved_in_blocking_work():
    request_id = ContextVar("test_request_id", default=None)
    token = request_id.set("request-123")
    pool = execution.BoundedWorkExecutor(max_workers=1, timeout_seconds=1)
    try:
        assert await pool.run(request_id.get) == "request-123"
    finally:
        request_id.reset(token)
        pool.close()


@pytest.mark.asyncio
async def test_each_worker_gets_its_submission_context():
    request_id = ContextVar("separate_request_id", default=None)
    pool = execution.BoundedWorkExecutor(max_workers=1, timeout_seconds=1)
    try:
        token = request_id.set("first")
        first = await pool.run(request_id.get)
        request_id.reset(token)
        token = request_id.set("second")
        second = await pool.run(request_id.get)
        request_id.reset(token)
        assert (first, second) == ("first", "second")
    finally:
        pool.close()


@pytest.mark.asyncio
async def test_capacity_is_retained_after_timeout():
    entered, release = Event(), Event()
    pool = execution.BoundedWorkExecutor(max_workers=1, timeout_seconds=0.05)

    def slow():
        entered.set()
        release.wait(3)

    try:
        with pytest.raises(errors.WorkTimeoutError):
            await pool.run(slow)
        assert entered.is_set()
        with pytest.raises(errors.WorkCapacityError):
            await pool.run(lambda: "must not run")
        release.set()
        # Wait for the real future to release its slot, rather than assuming timing.
        for _ in range(100):
            try:
                assert await pool.run(lambda: "available") == "available"
                break
            except errors.WorkCapacityError:
                await asyncio.sleep(0.01)
        else:
            pytest.fail("Completed work did not release capacity")
    finally:
        release.set()
        pool.close()


@pytest.mark.asyncio
async def test_cancelled_request_does_not_release_running_slot():
    entered, release = Event(), Event()
    pool = execution.BoundedWorkExecutor(max_workers=1, timeout_seconds=2)

    def slow():
        entered.set()
        release.wait(3)

    pending = asyncio.create_task(pool.run(slow))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        with pytest.raises(errors.WorkCapacityError):
            await pool.run(lambda: None)
    finally:
        release.set()
        pool.close()


@pytest.mark.asyncio
async def test_exclusive_mutations_are_serialized_and_failures_release_slots():
    entered, release = Event(), Event()
    pool = execution.BoundedWorkExecutor(max_workers=2, timeout_seconds=2)

    def mutate():
        entered.set()
        release.wait(3)

    pending = asyncio.create_task(pool.run(mutate, exclusive=True))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(errors.WorkCapacityError):
            await pool.run(lambda: None, exclusive=True)
        assert await pool.run(lambda: "read") == "read"
        release.set()
        await pending

        def fail():
            raise ValueError("operation failed")

        with pytest.raises(ValueError, match="operation failed"):
            await pool.run(fail, exclusive=True)
        assert await pool.run(lambda: "recovered", exclusive=True) == "recovered"
    finally:
        release.set()
        pool.close()
