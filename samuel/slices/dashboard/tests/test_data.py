"""Tests for the new Phase 14.6 data-layer helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from samuel.core.ports import IConfig
from samuel.slices.dashboard.data import (
    get_llm_routing,
    get_tamper_events,
)


class _Cfg(IConfig):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        pass


def _write_audit(tmp_path: Path, events: list[dict]) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "agent.jsonl", "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


class TestGetLLMRouting:
    def test_no_config_returns_default_row(self) -> None:
        rows = get_llm_routing(None)
        assert rows == [{"task": "default", "provider": "-", "model": "-"}]

    def test_default_only(self) -> None:
        cfg = _Cfg({"llm.default.provider": "deepseek", "llm.default.model": "deepseek-chat"})
        rows = get_llm_routing(cfg)
        assert rows == [{"task": "default", "provider": "deepseek", "model": "deepseek-chat"}]

    def test_task_specific_overrides_included(self) -> None:
        cfg = _Cfg({
            "llm.default.provider": "deepseek",
            "llm.default.model": "deepseek-chat",
            "llm.tasks.planning.provider": "claude",
            "llm.tasks.planning.model": "claude-sonnet-4-6",
            "llm.tasks.pr_review.provider": "ollama",
        })
        rows = get_llm_routing(cfg)
        assert {r["task"] for r in rows} == {"planning", "pr_review"}
        planning = next(r for r in rows if r["task"] == "planning")
        assert planning["provider"] == "claude"
        assert planning["model"] == "claude-sonnet-4-6"
        review = next(r for r in rows if r["task"] == "pr_review")
        assert review["provider"] == "ollama"
        assert review["model"] == "deepseek-chat"  # fallback to default


class TestGetTamperEvents:
    def test_tamper_message_names_detected(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "2026-04-17T10:00", "name": "x", "payload": {"message_name": "PlanCreated"}},
            {"ts": "2026-04-17T10:01", "name": "x", "payload": {"message_name": "TamperDetected", "reason": "bad"}},
            {"ts": "2026-04-17T10:02", "name": "x", "payload": {"message_name": "UnauthorizedChange"}},
            {"ts": "2026-04-17T10:03", "name": "x", "payload": {"message_name": "IntegrityViolation"}},
        ])
        events = get_tamper_events(str(tmp_path))
        names = [e["event"] for e in events]
        # Newest first
        assert names == ["IntegrityViolation", "UnauthorizedChange", "TamperDetected"]
        assert events[2]["detail"] == "bad"

    def test_broken_trust_boundaries_matched_via_owasp(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "x", "payload": {"message_name": "Whatever", "owasp_risk": "broken_trust_boundaries"}},
        ])
        events = get_tamper_events(str(tmp_path))
        assert len(events) == 1
        assert events[0]["owasp"] == "broken_trust_boundaries"

    def test_empty_when_no_matches(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "x", "payload": {"message_name": "PlanCreated"}},
        ])
        events = get_tamper_events(str(tmp_path))
        assert events == []

    def test_limit_applied(self, tmp_path: Path) -> None:
        many = [
            {"ts": f"t{i}", "name": "x", "payload": {"message_name": "TamperDetected"}}
            for i in range(30)
        ]
        _write_audit(tmp_path, many)
        events = get_tamper_events(str(tmp_path), limit=20)
        assert len(events) == 20
