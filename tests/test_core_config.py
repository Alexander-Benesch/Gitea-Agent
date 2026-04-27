from __future__ import annotations

import json
import tempfile
from pathlib import Path

from samuel.core.config import (
    AuditSchema,
    EvalSchema,
    FileConfig,
    GatesSchema,
    HooksSchema,
    WorkflowSchema,
    WorkflowStepSchema,
)


def test_workflow_schema():
    ws = WorkflowSchema(
        name="default",
        steps=[WorkflowStepSchema(on="IssueReady", send="PlanIssue")],
    )
    assert ws.name == "default"
    assert len(ws.steps) == 1
    assert ws.max_risk == 3
    assert ws.max_parallel == 1


def test_gates_schema():
    gs = GatesSchema(gates=[])
    assert gs.gates == []


def test_eval_schema_defaults():
    es = EvalSchema()
    assert es.min_score == 0.6
    assert es.criteria == []


def test_audit_schema():
    a = AuditSchema()
    assert a.sinks == []


def test_hooks_schema():
    h = HooksSchema()
    assert h.hooks == []


def test_file_config_load():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({"log_level": "DEBUG", "features": {"healing": True}}))
        config = FileConfig(d)
        assert config.get("agent.log_level") == "DEBUG"
        assert config.get("agent.features.healing") is True
        assert config.feature_flag("healing") is False  # feature_flag looks at top-level "features" key


def test_file_config_nested_key():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "scm.json"
        cfg.write_text(json.dumps({"provider": "gitea", "url": "http://localhost:3001"}))
        config = FileConfig(d)
        assert config.get("scm.provider") == "gitea"
        assert config.get("scm.missing", "default") == "default"


def test_file_config_missing_dir():
    config = FileConfig("/nonexistent/path")
    assert config.get("anything") is None


def test_file_config_reload():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({"val": 1}))
        config = FileConfig(d)
        assert config.get("agent.val") == 1
        cfg.write_text(json.dumps({"val": 2}))
        config.reload()
        assert config.get("agent.val") == 2
