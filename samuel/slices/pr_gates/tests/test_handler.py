from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import CreatePRCommand
from samuel.core.events import Event
from samuel.core.ports import IExternalGate, IVersionControl
from samuel.core.types import PR, Comment, GateContext, GateResult, Issue
from samuel.slices.pr_gates.handler import PRGatesHandler


class MockSCM(IVersionControl):
    def __init__(self, plan_comment: str = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] h.py"):
        self._plan = plan_comment

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return [Comment(id=1, body=self._plan, user="bot")]

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestPRGatesHandler:
    def test_all_gates_pass(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [1,2,3,4,5,6,7,8,9,10,11,12,"13a","13b"], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True
        assert any(e.name == "PRCreated" for e in events)

    def test_required_gate_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [1], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is False
        assert any(e.name == "GateFailed" for e in events)
        assert not any(e.name == "PRCreated" for e in events)

    def test_optional_gate_warns_but_passes(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [1], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is True
        assert any(e.name == "PRCreated" for e in events)

    def test_disabled_gate_skipped(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [1], "optional": [], "disabled": [1], "custom": []}')
        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is True

    def test_no_config_defaults_to_all_required(self, tmp_path: Path):
        bus = Bus()
        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path / "nonexistent"))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result is not None

    def test_correlation_id_flows(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [1], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        handler.handle(CreatePRCommand(issue_number=42, branch="main", correlation_id="gate-corr-1"))

        for e in events:
            assert e.correlation_id == "gate-corr-1"

    def test_external_gate_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class FailingGate(IExternalGate):
            name = "secrets_scan"
            def run(self, context: GateContext) -> GateResult:
                return GateResult(gate="secrets_scan", passed=False, reason="Secrets found")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(
            bus, scm=MockSCM(), config_dir=str(tmp_path),
            external_gates=[FailingGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is False
        assert any(e.name == "GateFailed" for e in events)

    def test_external_gate_passes(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class PassingGate(IExternalGate):
            name = "lint_check"
            def run(self, context: GateContext) -> GateResult:
                return GateResult(gate="lint_check", passed=True, reason="All clean")

        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(
            bus, scm=MockSCM(), config_dir=str(tmp_path),
            external_gates=[PassingGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True

    def test_external_gate_exception_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class BrokenGate(IExternalGate):
            name = "broken"
            def run(self, context: GateContext) -> GateResult:
                raise ConnectionError("timeout")

        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(
            bus, scm=MockSCM(), config_dir=str(tmp_path),
            external_gates=[BrokenGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is False

    def test_pr_created_on_scm(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class PRCreatingSCM(MockSCM):
            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                return PR(id=1, number=99, title=title, html_url="http://gitea/pr/99")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=PRCreatingSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        assert result["pr_number"] == 99
        assert result["pr_url"] == "http://gitea/pr/99"

        pr_event = next(e for e in events if e.name == "PRCreated")
        assert pr_event.payload["pr_number"] == 99
        assert pr_event.payload["pr_url"] == "http://gitea/pr/99"

    def test_pr_creation_failure_still_publishes_event(self, tmp_path: Path):
        """If SCM.create_pr raises, gates still pass and PRCreated is published."""
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        assert "pr_number" not in result
        assert any(e.name == "PRCreated" for e in events)
