from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import RunQualityCommand
from samuel.core.ports import IQualityCheck
from samuel.slices.quality.handler import QualityHandler


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class StubPassCheck(IQualityCheck):
    supported_extensions = {".py"}

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any:
        return {"passed": True}


class StubFailCheck(IQualityCheck):
    supported_extensions = {".py"}

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any:
        return {"passed": False, "reason": "quality issue found"}


class TestQualityHandlerPass:
    def test_pass_when_no_checks(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is True
        event_names = [e.name for e in events]
        assert "QualityPassed" in event_names

    def test_pass_with_passing_check(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def foo(): pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[StubPassCheck()], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is True
        event_names = [e.name for e in events]
        assert "QualityPassed" in event_names
        assert "QualityFailed" not in event_names


class TestQualityHandlerFail:
    def test_fail_when_file_missing(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["nonexistent.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is False
        assert result["results"][0]["reason"] == "not found"
        event_names = [e.name for e in events]
        assert "QualityFailed" in event_names

    def test_fail_with_failing_check(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("bad code\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[StubFailCheck()], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is False
        event_names = [e.name for e in events]
        assert "QualityFailed" in event_names
        assert "QualityPassed" not in event_names


class TestQualityEvents:
    def test_quality_passed_event_contains_issue(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 99})
        handler.handle(cmd)

        passed_events = [e for e in events if e.name == "QualityPassed"]
        assert len(passed_events) == 1
        assert passed_events[0].payload["issue"] == 99

    def test_quality_failed_event_contains_failures(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["missing.py"], "issue": 7})
        handler.handle(cmd)

        failed_events = [e for e in events if e.name == "QualityFailed"]
        assert len(failed_events) == 1
        assert len(failed_events[0].payload["failures"]) >= 1

    def test_correlation_id_propagated(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(
            payload={"files": ["handler.py"], "issue": 1},
            correlation_id="corr-123",
        )
        handler.handle(cmd)

        passed_events = [e for e in events if e.name == "QualityPassed"]
        assert passed_events[0].correlation_id == "corr-123"

    def test_empty_files_list_passes(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": [], "issue": 1})
        result = handler.handle(cmd)

        assert result["passed"] is True
        event_names = [e.name for e in events]
        assert "QualityPassed" in event_names

    def test_check_extension_mismatch_skipped(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("# Hello\n")
        bus = Bus()
        _collect_events(bus)
        # StubFailCheck only supports .py, so .md files skip it
        handler = QualityHandler(bus, checks=[StubFailCheck()], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["readme.md"], "issue": 1})
        result = handler.handle(cmd)

        assert result["passed"] is True
