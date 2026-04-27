from __future__ import annotations

from datetime import datetime, timezone

from samuel.core.events import (
    AuditEvent,
    CheckpointSaved,
    CodeGenerated,
    CommandDeduplicated,
    ConfigReloaded,
    EvalCompleted,
    EvalFailed,
    Event,
    GateFailedEvent,
    IssueReady,
    LLMCallCompleted,
    LLMUnavailable,
    PlanApproved,
    PlanBlocked,
    PlanCreated,
    PlanFeedbackReceived,
    PlanPosted,
    PlanValidated,
    PRCreated,
    PreCommitCheckCompleted,
    ProviderCircuitOpen,
    QualityFailed,
    QualityPassed,
    SecurityTripwireTriggered,
    StartupBlocked,
    TokenLimitHit,
    UnhandledCommand,
    WorkflowAborted,
    WorkflowBlocked,
)


def test_event_base_fields():
    e = Event(name="TestEvent")
    assert e.name == "TestEvent"
    assert e.event_version == 1
    assert e.causation_id is None
    assert isinstance(e.ts, datetime)
    assert e.ts.tzinfo == timezone.utc
    assert len(e.correlation_id) == 36  # UUID


def test_event_uses_utc():
    e = IssueReady(payload={"number": 1})
    assert e.ts.tzinfo == timezone.utc


def test_all_event_types_instantiable():
    event_classes = [
        IssueReady, PlanCreated, PlanValidated, PlanBlocked, PlanPosted,
        PlanApproved, PlanFeedbackReceived, CodeGenerated, QualityPassed,
        QualityFailed, PRCreated, GateFailedEvent, EvalCompleted, EvalFailed,
        WorkflowBlocked, WorkflowAborted, LLMUnavailable, TokenLimitHit,
        ConfigReloaded, CommandDeduplicated, UnhandledCommand, AuditEvent,
        SecurityTripwireTriggered, PreCommitCheckCompleted, StartupBlocked,
        ProviderCircuitOpen, CheckpointSaved, LLMCallCompleted,
    ]
    for cls in event_classes:
        e = cls()
        assert e.name != ""
        assert e.event_version == 1


def test_event_correlation_propagation():
    parent = IssueReady(payload={"number": 42})
    child = PlanCreated(
        correlation_id=parent.correlation_id,
        causation_id=parent.correlation_id,
    )
    assert child.correlation_id == parent.correlation_id
    assert child.causation_id == parent.correlation_id
