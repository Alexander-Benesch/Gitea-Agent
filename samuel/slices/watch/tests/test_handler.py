from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import ScanIssuesCommand
from samuel.core.events import Event
from samuel.core.ports import IConfig, IVersionControl
from samuel.core.types import Comment, Issue, Label
from samuel.slices.watch.handler import (
    LABEL_APPROVED,
    LABEL_PLAN,
    WatchHandler,
)


class MockSCM(IVersionControl):
    def __init__(self, issues_by_label: dict[str, list[Issue]] | None = None):
        self._issues = issues_by_label or {}
        self.label_swaps: list[tuple[int, str, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        self.label_swaps.append((number, remove, add))

    def list_issues(self, labels: list[str]) -> list[Issue]:
        key = labels[0] if labels else ""
        return self._issues.get(key, [])

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


class MockConfig(IConfig):
    def __init__(self) -> None:
        self.reload_count = 0

    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        self.reload_count += 1


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestWatchHandler:
    def test_dispatches_approved_issues(self):
        issues = {LABEL_APPROVED: [
            Issue(number=10, title="A", body="", state="open"),
            Issue(number=11, title="B", body="", state="open"),
        ]}
        scm = MockSCM(issues)
        bus = Bus()
        bus.register_command("PlanIssue", lambda cmd: None)
        events = _collect_events(bus)

        handler = WatchHandler(bus, scm=scm, max_parallel=5)
        result = handler.handle(ScanIssuesCommand())

        assert result["dispatched"] == 2
        issue_ready = [e for e in events if e.name == "IssueReady"]
        assert len(issue_ready) == 2

    def test_semaphore_limits_concurrency(self):
        issues = {LABEL_APPROVED: [
            Issue(number=i, title=f"Issue {i}", body="", state="open")
            for i in range(5)
        ]}
        scm = MockSCM(issues)
        bus = Bus()
        bus.register_command("PlanIssue", lambda cmd: None)

        handler = WatchHandler(bus, scm=scm, max_parallel=1)
        result = handler.handle(ScanIssuesCommand())

        assert result["dispatched"] == 5

    def test_no_scm_returns_zero(self):
        bus = Bus()
        handler = WatchHandler(bus, scm=None)
        result = handler.handle(ScanIssuesCommand())
        assert result["dispatched"] == 0

    def test_hot_reload_called(self):
        scm = MockSCM()
        config = MockConfig()
        bus = Bus()

        handler = WatchHandler(bus, scm=scm, config=config)
        handler.handle(ScanIssuesCommand())

        assert config.reload_count == 1

    def test_label_consistency_fixes_duplicates(self):
        issues_plan = [
            Issue(
                number=42, title="X", body="", state="open",
                labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
            ),
        ]
        scm = MockSCM({LABEL_PLAN: issues_plan, LABEL_APPROVED: []})
        bus = Bus()

        handler = WatchHandler(bus, scm=scm)
        result = handler.handle(ScanIssuesCommand())

        assert result["label_fixes"] >= 1
        assert len(scm.label_swaps) >= 1

    def test_correlation_id_flows(self):
        issues = {LABEL_APPROVED: [
            Issue(number=10, title="A", body="", state="open"),
        ]}
        scm = MockSCM(issues)
        bus = Bus()
        bus.register_command("PlanIssue", lambda cmd: None)
        events = _collect_events(bus)

        handler = WatchHandler(bus, scm=scm)
        handler.handle(ScanIssuesCommand(correlation_id="watch-corr-1"))

        for e in events:
            if e.name == "IssueReady":
                assert e.correlation_id == "watch-corr-1"

    def test_empty_approved_list(self):
        scm = MockSCM({LABEL_APPROVED: []})
        bus = Bus()

        handler = WatchHandler(bus, scm=scm)
        result = handler.handle(ScanIssuesCommand())

        assert result["dispatched"] == 0
