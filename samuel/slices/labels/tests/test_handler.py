from __future__ import annotations

import pytest

from samuel.core.bus import Bus
from samuel.core.events import (
    CodeGenerated,
    Event,
    GateFailedEvent,
    PlanBlocked,
    PlanCreated,
    PlanValidated,
    PRCreated,
    WorkflowBlocked,
)
from samuel.core.ports import IVersionControl
from samuel.core.types import PR, Comment, Issue
from samuel.slices.labels.handler import LabelsHandler


class FakeSCM(IVersionControl):
    def __init__(self) -> None:
        self.swap_calls: list[tuple[int, str, str]] = []
        self.fail_on: set[tuple[str, str]] = set()

    def swap_label(self, number: int, remove: str, add: str) -> None:
        if (remove, add) in self.fail_on:
            raise RuntimeError("simulated failure")
        self.swap_calls.append((number, remove, add))

    # Unused — stubs to satisfy ABC
    def get_issue(self, number: int) -> Issue: ...
    def get_comments(self, number: int) -> list[Comment]: return []
    def post_comment(self, number: int, body: str) -> Comment: ...
    def create_pr(self, head: str, base: str, title: str, body: str) -> PR: ...
    def list_labels(self) -> list[dict]: return []
    def create_label(self, name: str, color: str, description: str = "") -> dict: return {}
    def list_issues(self, labels: list[str]) -> list[Issue]: return []
    def close_issue(self, number: int) -> None: ...
    def merge_pr(self, pr_id: int) -> bool: return True
    def issue_url(self, number: int) -> str: return ""
    def pr_url(self, pr_id: int) -> str: return ""
    def branch_url(self, branch: str) -> str: return ""


@pytest.fixture
def bus() -> Bus:
    return Bus()


@pytest.fixture
def scm() -> FakeSCM:
    return FakeSCM()


@pytest.fixture
def handler(bus: Bus, scm: FakeSCM) -> LabelsHandler:
    h = LabelsHandler(bus, scm=scm)
    h.register()
    return h


class TestTransitions:
    def test_issue_ready_adds_ready_for_agent(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(Event(name="IssueReady", payload={"issue_number": 42}))
        assert (42, "", "ready-for-agent") in scm.swap_calls

    def test_plan_created_adds_status_plan(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(PlanCreated(payload={"issue": 42}))
        assert (42, "", "status:plan") in scm.swap_calls

    def test_plan_validated_adds_status_approved(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(PlanValidated(payload={"issue": 42}))
        assert (42, "", "status:approved") in scm.swap_calls

    def test_code_generated_swaps_ready_to_in_progress_and_wip(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(CodeGenerated(payload={"issue": 42}))
        assert (42, "ready-for-agent", "in-progress") in scm.swap_calls
        assert (42, "", "status:wip") in scm.swap_calls

    def test_pr_created_swaps_in_progress_to_needs_review(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PRCreated(payload={"issue": 42}))
        assert (42, "in-progress", "needs-review") in scm.swap_calls

    def test_plan_blocked_adds_help_wanted(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(PlanBlocked(payload={"issue": 42}))
        assert (42, "", "help wanted") in scm.swap_calls

    def test_gate_failed_adds_help_wanted(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(GateFailedEvent(payload={"issue": 42}))
        assert (42, "", "help wanted") in scm.swap_calls

    def test_workflow_blocked_adds_help_wanted(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(WorkflowBlocked(payload={"issue": 42}))
        assert (42, "", "help wanted") in scm.swap_calls


class TestPayloadExtraction:
    def test_issue_number_from_issue_field(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(PlanCreated(payload={"issue": 7}))
        assert any(c[0] == 7 for c in scm.swap_calls)

    def test_issue_number_from_issue_number_field(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(Event(name="IssueReady", payload={"issue_number": 8}))
        assert any(c[0] == 8 for c in scm.swap_calls)

    def test_issue_number_as_string_is_accepted(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(PlanCreated(payload={"issue": "9"}))
        assert any(c[0] == 9 for c in scm.swap_calls)

    def test_no_issue_number_skips_silently(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(PlanCreated(payload={}))
        assert scm.swap_calls == []


class TestErrorHandling:
    def test_scm_failure_is_swallowed(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        scm.fail_on.add(("", "ready-for-agent"))
        bus.publish(Event(name="IssueReady", payload={"issue_number": 42}))

    def test_no_scm_skips(self, bus: Bus) -> None:
        h = LabelsHandler(bus, scm=None)
        h.register()
        bus.publish(PlanCreated(payload={"issue": 1}))


class TestNoRegression:
    def test_unrelated_event_triggers_nothing(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(Event(name="SomeUnrelatedEvent", payload={"issue": 42}))
        assert scm.swap_calls == []
