from __future__ import annotations

from typing import Any

from samuel.core.bus import AuditMiddleware, Bus, ErrorMiddleware
from samuel.core.commands import PlanIssueCommand
from samuel.core.events import (
    Event,
)
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse
from samuel.slices.planning.handler import PlanningHandler

GOOD_PLAN = """\
## Analyse
Änderung in `handler.py` Zeile 42.

### Akzeptanzkriterien
- [ ] [DIFF] handler.py — Handler geändert
- [ ] [TEST] test_handler — Tests grün
"""

BAD_PLAN = "Kein Plan."


class FakeSCM(IVersionControl):
    def __init__(self, issue_body: str = "- [ ] AC1\n- [ ] AC2", labels: list | None = None):
        self._issue_body = issue_body
        self._labels = labels or []
        self.posted_comments: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(
            number=number,
            title=f"Test Issue #{number}",
            body=self._issue_body,
            state="open",
            labels=self._labels,
        )

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted_comments.append((number, body))
        return Comment(id=len(self.posted_comments), body=body, user="bot")

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
        return f"http://test/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"http://test/pulls/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"http://test/branch/{branch}"

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class FakeLLM(ILLMProvider):
    def __init__(self, text: str):
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200000


class AuditSink:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    def write(self, event: Any) -> None:
        self.entries.append(event)


def _setup_bus_with_handler(
    plan_text: str, issue_body: str = "- [ ] AC1\n- [ ] AC2"
) -> tuple[Bus, FakeSCM, list[Event], AuditSink]:
    bus = Bus()
    audit_sink = AuditSink()
    bus.add_middleware(AuditMiddleware(sink=audit_sink))
    bus.add_middleware(ErrorMiddleware())

    scm = FakeSCM(issue_body=issue_body)
    llm = FakeLLM(plan_text)
    handler = PlanningHandler(bus, scm=scm, llm=llm)
    bus.register_command("PlanIssue", handler.handle)

    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))

    return bus, scm, events, audit_sink


class TestIntegrationHappyPath:
    def test_full_plan_flow(self):
        bus, scm, events, audit = _setup_bus_with_handler(GOOD_PLAN)

        cmd = PlanIssueCommand(issue_number=42, idempotency_key="plan:42")
        result = bus.send(cmd)

        assert result is not None
        assert result["score"] >= 50

        event_names = [e.name for e in events]
        assert "PlanCreated" in event_names
        assert "PlanValidated" in event_names
        assert "PlanPosted" in event_names

        assert len(scm.posted_comments) == 1
        assert scm.posted_comments[0][0] == 42
        assert "## Plan für Issue #42" in scm.posted_comments[0][1]

    def test_correlation_id_flows_through_all_events(self):
        bus, scm, events, audit = _setup_bus_with_handler(GOOD_PLAN)

        cmd = PlanIssueCommand(
            issue_number=42,
            correlation_id="integration-test-corr",
        )
        bus.send(cmd)

        plan_events = [e for e in events if e.name.startswith("Plan")]
        assert len(plan_events) >= 2
        for e in plan_events:
            assert e.correlation_id == "integration-test-corr"

    def test_audit_log_records_events(self):
        bus, scm, events, audit = _setup_bus_with_handler(GOOD_PLAN)

        bus.send(PlanIssueCommand(issue_number=42))

        audit_names = [e.payload.get("message_name") for e in audit.entries]
        assert "PlanCreated" in audit_names
        assert "PlanPosted" in audit_names


class TestIntegrationBadPlan:
    def test_bad_plan_no_scm_post(self):
        bus, scm, events, audit = _setup_bus_with_handler(BAD_PLAN)

        result = bus.send(PlanIssueCommand(issue_number=42))

        assert result is not None
        assert result["score"] < 50

        event_names = [e.name for e in events]
        assert "PlanBlocked" in event_names
        assert "PlanPosted" not in event_names

        assert len(scm.posted_comments) == 0

    def test_blocked_event_has_issue_number(self):
        bus, scm, events, audit = _setup_bus_with_handler(BAD_PLAN)

        bus.send(PlanIssueCommand(issue_number=99))

        blocked = [e for e in events if e.name == "PlanBlocked"]
        assert len(blocked) >= 1
        assert blocked[0].payload["issue"] == 99


class TestIntegrationViaBusSend:
    def test_bus_send_triggers_handler(self):
        bus, scm, events, audit = _setup_bus_with_handler(GOOD_PLAN)

        cmd = PlanIssueCommand(issue_number=42)
        result = bus.send(cmd)

        assert result is not None
        assert any(e.name == "PlanPosted" for e in events)
