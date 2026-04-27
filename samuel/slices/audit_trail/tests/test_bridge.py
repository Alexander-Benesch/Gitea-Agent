from __future__ import annotations

import json
import tempfile
from pathlib import Path

from samuel.core.bus import Bus
from samuel.slices.audit_trail.bridge import (
    log_event,
    set_bus,
    set_correlation_id,
    set_jsonl_path,
)
from samuel.slices.audit_trail.owasp import classify as _owasp_risk


def setup_function():
    set_bus(None)
    set_correlation_id(None)


def test_log_event_publishes_to_bus():
    bus = Bus()
    received = []
    bus.subscribe("AuditEvent", lambda e: received.append(e))
    set_bus(bus)

    event_id = log_event("session_start", "system", "Agent started")
    assert len(received) == 1
    assert received[0].payload["evt"] == "session_start"
    assert received[0].payload["cat"] == "system"
    assert received[0].payload["event_id"] == event_id


def test_log_event_with_correlation_id():
    bus = Bus()
    received = []
    bus.subscribe("AuditEvent", lambda e: received.append(e))
    set_bus(bus)
    set_correlation_id("corr-42")

    log_event("llm_call", "llm", "Called model")
    assert received[0].correlation_id == "corr-42"


def test_log_event_with_causation():
    bus = Bus()
    received = []
    bus.subscribe("AuditEvent", lambda e: received.append(e))
    set_bus(bus)

    log_event("pr_create", "scm", "PR created", caused_by="evt-123")
    assert received[0].causation_id == "evt-123"


def test_log_event_fallback_jsonl():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "audit.jsonl"
        set_jsonl_path(path)
        set_bus(None)

        event_id = log_event("session_start", "system", "Agent started", issue=42)
        assert path.exists()
        line = json.loads(path.read_text().strip())
        assert line["id"] == event_id
        assert line["evt"] == "session_start"
        assert line["issue"] == 42
        assert "correlation_id" in line
        assert "ts" in line


def test_log_event_signature_matches_v1():
    bus = Bus()
    received = []
    bus.subscribe("AuditEvent", lambda e: received.append(e))
    set_bus(bus)

    log_event(
        "git_commit", "scm", "Committed changes",
        lvl="info", issue=42, step="implement",
        branch="feat/x", trigger="watch",
        source="agent", caused_by="evt-1",
        parent_evt="evt-0", meta={"files": 3},
    )
    p = received[0].payload
    assert p["issue"] == 42
    assert p["step"] == "implement"
    assert p["branch"] == "feat/x"
    assert p["trigger"] == "watch"
    assert p["source"] == "agent"
    assert p["meta"] == {"files": 3}


def test_owasp_risk_exact_match():
    assert _owasp_risk("scm", "git_commit") == "broken_trust_boundaries"
    assert _owasp_risk("guard", "quality_check") == "inadequate_sandboxing"


def test_owasp_risk_cat_fallback():
    assert _owasp_risk("llm", "unknown_event") == "unmonitored_activities"


def test_owasp_risk_unknown():
    assert _owasp_risk("unknown_cat", "unknown_evt") is None


def test_owasp_risk_in_payload():
    bus = Bus()
    received = []
    bus.subscribe("AuditEvent", lambda e: received.append(e))
    set_bus(bus)

    log_event("git_commit", "scm", "Committed")
    assert received[0].payload["owasp_risk"] == "broken_trust_boundaries"
