from __future__ import annotations

from samuel.core.bus import Bus
from samuel.core.events import Event, IssueReady
from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery


class MockSink(IAuditSink):
    def __init__(self):
        self.written: list[dict] = []

    def write(self, event):
        self.written.append(event)

    def query(self, query: AuditQuery) -> list:
        return []


class FailingSink(IAuditSink):
    def write(self, event):
        raise RuntimeError("sink broken")

    def query(self, query: AuditQuery) -> list:
        return []


def test_handler_receives_all_events():
    from samuel.slices.audit_trail.handler import AuditHandler

    bus = Bus()
    sink = MockSink()
    handler = AuditHandler(sinks=[sink])
    handler.register(bus)

    bus.publish(IssueReady(payload={"number": 1}))
    bus.publish(Event(name="CustomEvent", payload={"foo": "bar"}))

    assert len(sink.written) == 2


def test_handler_includes_correlation_id():
    from samuel.slices.audit_trail.handler import AuditHandler

    bus = Bus()
    sink = MockSink()
    handler = AuditHandler(sinks=[sink])
    handler.register(bus)

    bus.publish(IssueReady(correlation_id="corr-99", payload={"number": 1}))
    assert sink.written[0]["correlation_id"] == "corr-99"


def test_handler_owasp_classification():
    from samuel.slices.audit_trail.handler import AuditHandler

    bus = Bus()
    sink = MockSink()
    handler = AuditHandler(sinks=[sink])
    handler.register(bus)

    bus.publish(Event(name="test", payload={"cat": "scm", "evt": "git_commit"}))
    assert sink.written[0]["owasp_risk"] == "broken_trust_boundaries"


def test_handler_multiple_sinks():
    from samuel.slices.audit_trail.handler import AuditHandler

    bus = Bus()
    sink1 = MockSink()
    sink2 = MockSink()
    handler = AuditHandler(sinks=[sink1, sink2])
    handler.register(bus)

    bus.publish(Event(name="test", payload={}))
    assert len(sink1.written) == 1
    assert len(sink2.written) == 1


def test_handler_sink_failure_doesnt_break_others():
    from samuel.slices.audit_trail.handler import AuditHandler

    bus = Bus()
    failing = FailingSink()
    good = MockSink()
    handler = AuditHandler(sinks=[failing, good])
    handler.register(bus)

    bus.publish(Event(name="test", payload={}))
    assert len(good.written) == 1
