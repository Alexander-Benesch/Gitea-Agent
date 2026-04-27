from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from samuel.adapters.audit.jsonl import JSONLAuditSink
from samuel.adapters.audit.upcasters import upcast
from samuel.core.types import AuditQuery


def test_write_and_read():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "IssueReady", "correlation_id": "c1", "payload": {"issue": 42}})
        sink.write({"event_name": "PlanCreated", "correlation_id": "c1", "payload": {"issue": 42}})

        results = sink.query(AuditQuery(issue=42))
        assert len(results) == 2


def test_query_by_correlation_id():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "A", "correlation_id": "c1", "payload": {}})
        sink.write({"event_name": "B", "correlation_id": "c2", "payload": {}})

        results = sink.query(AuditQuery(correlation_id="c1"))
        assert len(results) == 1
        assert results[0]["correlation_id"] == "c1"


def test_query_by_event_name():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "IssueReady", "correlation_id": "c1", "payload": {}})
        sink.write({"event_name": "PlanCreated", "correlation_id": "c1", "payload": {}})

        results = sink.query(AuditQuery(event_name="IssueReady"))
        assert len(results) == 1


def test_query_by_owasp_risk():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "A", "owasp_risk": "broken_trust_boundaries", "payload": {}})
        sink.write({"event_name": "B", "owasp_risk": "excessive_autonomy", "payload": {}})

        results = sink.query(AuditQuery(owasp_risk="broken_trust_boundaries"))
        assert len(results) == 1


def test_query_limit():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        for i in range(10):
            sink.write({"event_name": "E", "correlation_id": "c", "payload": {}})

        results = sink.query(AuditQuery(limit=3))
        assert len(results) == 3


def test_daily_rotation():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="daily")
        sink.write({"event_name": "Test", "payload": {}})

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expected = Path(d) / f"audit_{date_str}.jsonl"
        assert expected.exists()


def test_no_rotation():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write({"event_name": "Test", "payload": {}})
        assert (Path(d) / "audit.jsonl").exists()


def test_upcast_gate_failed():
    event = {"name": "GateFailed", "event_version": 1, "gate": 3}
    result = upcast(event)
    assert result["owasp_risk"] == "unknown"
    assert result["event_version"] == 2


def test_upcast_llm_call_completed():
    event = {"name": "LLMCallCompleted", "event_version": 1, "text": "hi"}
    result = upcast(event)
    assert result["latency_ms"] == 0
    assert result["event_version"] == 2


def test_upcast_no_match():
    event = {"name": "IssueReady", "event_version": 1}
    result = upcast(event)
    assert result == event


def test_write_adds_timestamp():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write({"event_name": "Test", "payload": {}})
        line = json.loads((Path(d) / "audit.jsonl").read_text().strip())
        assert "ts" in line
