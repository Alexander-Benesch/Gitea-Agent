from __future__ import annotations

from samuel.core.bus import Bus
from samuel.core.events import EvalCompleted, IssueReady
from samuel.core.workflow import WorkflowEngine


def test_workflow_dispatches_command():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(c.payload))

    definition = {
        "steps": [{"on": "IssueReady", "send": "PlanIssue"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"number": 42}))
    assert len(results) == 1
    assert results[0]["number"] == 42


def test_workflow_unhandled_command():
    bus = Bus()
    unhandled = []
    bus.subscribe("UnhandledCommand", lambda e: unhandled.append(e))

    definition = {
        "steps": [{"on": "IssueReady", "send": "NonExistent"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={}))
    assert len(unhandled) == 1
    assert unhandled[0].payload["command"] == "NonExistent"


def test_workflow_condition_blocks():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "IssueReady", "send": "PlanIssue", "condition": "payload.get('priority') == 'high'"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"priority": "low"}))
    assert len(results) == 0


def test_workflow_condition_passes():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "IssueReady", "send": "PlanIssue", "condition": "payload.get('priority') == 'high'"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"priority": "high"}))
    assert len(results) == 1


def test_builtin_condition_self_parity_ok_passes():
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(c.payload))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(EvalCompleted(payload={"issue": 42, "eval_score": 0.8, "branch": "samuel/issue-42"}))
    assert len(results) == 1
    assert results[0]["branch"] == "samuel/issue-42"


def test_builtin_condition_self_parity_ok_blocks():
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(EvalCompleted(payload={"issue": 42, "eval_score": 0.3}))
    assert len(results) == 0


def test_builtin_condition_self_parity_ok_missing_score():
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(EvalCompleted(payload={"issue": 42}))
    assert len(results) == 0
