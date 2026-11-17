import asyncio
from threading import Event, get_ident

import pytest

from legal_rag.infrastructure.errors import WorkTimeoutError
from legal_rag.infrastructure.execution import BoundedWorkExecutor


class RecordingMonitoring:
    def __init__(self):
        self.events = []
        self.names = []
        self.kinds = []

    def run(self, name, operation, *, as_type="span"):
        self.names.append(name)
        self.kinds.append(as_type)
        self.events.append(("start", get_ident()))
        try:
            return operation()
        finally:
            self.events.append(("end", get_ident()))


@pytest.mark.asyncio
async def test_monitoring_runs_inside_worker_and_preserves_return_value():
    monitoring = RecordingMonitoring()
    pool = BoundedWorkExecutor(max_workers=1, timeout_seconds=1, monitoring=monitoring)
    original = {"answer": "unchanged"}
    try:
        assert (
            await pool.run(
                lambda: original, operation_name="answer-question", observation_type="chain"
            )
            is original
        )
        assert monitoring.names == ["answer-question"]
        assert monitoring.kinds == ["chain"]
        assert [event for event, _ in monitoring.events] == ["start", "end"]
        assert all(thread != get_ident() for _, thread in monitoring.events)
    finally:
        pool.close()


@pytest.mark.asyncio
async def test_timeout_does_not_end_monitoring_before_worker_finishes():
    monitoring = RecordingMonitoring()
    release, finished = Event(), Event()
    pool = BoundedWorkExecutor(max_workers=1, timeout_seconds=0.01, monitoring=monitoring)

    def slow():
        release.wait(2)
        finished.set()

    try:
        with pytest.raises(WorkTimeoutError):
            await pool.run(slow)
        assert [event for event, _ in monitoring.events] == ["start"]
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        for _ in range(100):
            if len(monitoring.events) == 2:
                break
            await asyncio.sleep(0.001)
        assert [event for event, _ in monitoring.events] == ["start", "end"]
    finally:
        release.set()
        pool.close()
