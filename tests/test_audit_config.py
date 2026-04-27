from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from samuel.core.config import AuditSchema, AuditSinkSchema, load_audit_config


def test_load_valid_audit_config():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "audit.json"
        cfg.write_text(json.dumps({
            "sinks": [
                {"type": "jsonl", "path": "data/logs/agent.jsonl", "rotation": "daily"},
                {"type": "webhook", "url": "https://siem.example.com/api", "auth": "bearer"},
            ]
        }))
        schema = load_audit_config(d)
        assert len(schema.sinks) == 2
        assert schema.sinks[0].type == "jsonl"
        assert schema.sinks[0].rotation == "daily"
        assert schema.sinks[1].type == "webhook"
        assert schema.sinks[1].url == "https://siem.example.com/api"


def test_load_missing_file_returns_default():
    with tempfile.TemporaryDirectory() as d:
        schema = load_audit_config(d)
        assert len(schema.sinks) == 1
        assert schema.sinks[0].type == "jsonl"
        assert schema.sinks[0].path == "data/logs/agent.jsonl"


def test_load_invalid_json_raises_valueerror():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "audit.json"
        cfg.write_text("not valid json")
        with pytest.raises(ValueError, match="Invalid audit.json"):
            load_audit_config(d)


def test_load_invalid_schema_raises_valueerror():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "audit.json"
        cfg.write_text(json.dumps({"sinks": [{"type": 123}]}))
        with pytest.raises(ValueError, match="validation failed"):
            load_audit_config(d)


def test_audit_sink_schema_optional_fields():
    s = AuditSinkSchema(type="elasticsearch", host="https://es:9200", index="samuel")
    assert s.path is None
    assert s.url is None
    assert s.auth is None
    assert s.host == "https://es:9200"
    assert s.index == "samuel"


def test_default_schema():
    schema = AuditSchema.default()
    assert len(schema.sinks) == 1
    assert schema.sinks[0].type == "jsonl"


def test_project_audit_json():
    schema = load_audit_config(Path(__file__).resolve().parent.parent / "config")
    assert len(schema.sinks) >= 1
    assert schema.sinks[0].type == "jsonl"
