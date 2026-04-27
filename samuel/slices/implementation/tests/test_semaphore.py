from __future__ import annotations

import threading

from samuel.core.bus import Bus
from samuel.core.events import (
    LLMUnavailable,
    PlanBlocked,
    PRCreated,
    WorkflowAborted,
    WorkflowBlocked,
)

TERMINAL_EVENTS = [
    "PRCreated",
    "WorkflowBlocked",
    "LLMUnavailable",
    "PlanBlocked",
    "WorkflowAborted",
]


class FakeSemaphore:
    def __init__(self, max_slots: int = 3):
        self._sem = threading.Semaphore(max_slots)
        self._max = max_slots
        self.release_count = 0

    def acquire(self) -> None:
        self._sem.acquire()

    def release(self) -> None:
        self._sem.release()
        self.release_count += 1

    @property
    def available(self) -> int:
        # Approximate: not perfectly thread-safe but sufficient for tests
        return self._sem._value


def wire_semaphore_release(bus: Bus, semaphore: FakeSemaphore) -> None:
    for event_name in TERMINAL_EVENTS:
        bus.subscribe(event_name, lambda _ev, sem=semaphore: sem.release())


class TestSemaphoreRelease:
    def test_each_terminal_event_releases(self):
        bus = Bus()
        sem = FakeSemaphore(max_slots=5)
        wire_semaphore_release(bus, sem)

        sem.acquire()
        sem.acquire()
        assert sem.available == 3

        bus.publish(WorkflowBlocked(payload={"issue": 1}))
        assert sem.available == 4

        bus.publish(PlanBlocked(payload={"issue": 2}))
        assert sem.available == 5

    def test_all_terminal_events_covered(self):
        bus = Bus()
        sem = FakeSemaphore(max_slots=10)
        wire_semaphore_release(bus, sem)

        for _ in range(5):
            sem.acquire()
        assert sem.available == 5

        event_classes = [PRCreated, WorkflowBlocked, LLMUnavailable, PlanBlocked, WorkflowAborted]
        for cls in event_classes:
            bus.publish(cls(payload={"test": True}))

        assert sem.release_count == 5
        assert sem.available == 10

    def test_no_leak_after_n_workflows(self):
        bus = Bus()
        sem = FakeSemaphore(max_slots=3)
        wire_semaphore_release(bus, sem)

        for i in range(10):
            sem.acquire()
            bus.publish(WorkflowBlocked(payload={"issue": i}))

        assert sem.available == 3
