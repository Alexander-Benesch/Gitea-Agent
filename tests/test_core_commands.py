from __future__ import annotations

from samuel.core.commands import (
    BuildContextCommand,
    ChangelogCommand,
    Command,
    CreatePRCommand,
    EvaluateCommand,
    HealCommand,
    HealthCheckCommand,
    ImplementCommand,
    PlanIssueCommand,
    ReloadConfigCommand,
    ReviewCommand,
    RunQualityCommand,
    ScanIssuesCommand,
    ShutdownCommand,
    VerifyACCommand,
)


def test_command_base_fields():
    c = Command(name="Test")
    assert c.name == "Test"
    assert c.idempotency_key is None
    assert c.correlation_id is not None
    assert len(c.correlation_id) == 36


def test_command_with_idempotency():
    c = CreatePRCommand(idempotency_key="pr:42:feat/x")
    assert c.name == "CreatePR"
    assert c.idempotency_key == "pr:42:feat/x"


def test_all_command_types_instantiable():
    cmd_classes = [
        ScanIssuesCommand, PlanIssueCommand, ImplementCommand,
        CreatePRCommand, EvaluateCommand, HealCommand, ReviewCommand,
        HealthCheckCommand, ReloadConfigCommand, ShutdownCommand,
        BuildContextCommand, RunQualityCommand, VerifyACCommand,
        ChangelogCommand,
    ]
    for cls in cmd_classes:
        c = cls()
        assert c.name != ""
        assert isinstance(c.payload, dict)
