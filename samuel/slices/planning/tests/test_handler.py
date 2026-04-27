from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import PlanIssueCommand
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse
from samuel.slices.planning.handler import (
    PlanningHandler,
    validate_plan,
    validate_plan_against_skeleton,
)

GOOD_PLAN = """\
## Analyse
Änderung in `handler.py` Zeile 42.

### Akzeptanzkriterien
- [ ] [DIFF] handler.py — Handler geändert
- [ ] [TEST] test_handler — Tests grün
"""

BAD_PLAN = "Hier ist ein Plan ohne jegliche Struktur."

MEDIUM_PLAN = """\
## Analyse
Änderung in `handler.py`.

### Akzeptanzkriterien
- [ ] [DIFF] handler.py — Handler geändert
- [ ] [INVALIDTAG] something — broken tag
"""


class MockSCM(IVersionControl):
    def __init__(self, issue: Issue | None = None):
        self._issue = issue or Issue(number=42, title="Test Issue", body="- [ ] AC1\n- [ ] AC2", state="open")
        self.posted_comments: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return self._issue

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted_comments.append((number, body))
        return Comment(id=1, body=body, user="bot")

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


class MockLLM(ILLMProvider):
    def __init__(self, response_text: str = GOOD_PLAN):
        self._text = response_text
        self.call_count = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200000


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestPlanningHandler:
    def test_happy_path(self):
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        events = _collect_events(bus)

        cmd = PlanIssueCommand(issue_number=42, idempotency_key="plan:42")
        result = handler.handle(cmd)

        assert result["score"] >= 50
        event_names = [e.name for e in events]
        assert "PlanCreated" in event_names
        assert "PlanValidated" in event_names
        assert "PlanPosted" in event_names
        assert len(scm.posted_comments) == 1
        assert scm.posted_comments[0][0] == 42

    def test_no_scm_publishes_blocked(self):
        bus = Bus()
        handler = PlanningHandler(bus, scm=None, llm=MockLLM())
        events = _collect_events(bus)

        result = handler.handle(PlanIssueCommand(issue_number=42))

        assert result is None
        assert any(e.name == "PlanBlocked" for e in events)

    def test_no_llm_publishes_blocked(self):
        bus = Bus()
        handler = PlanningHandler(bus, scm=MockSCM(), llm=None)
        events = _collect_events(bus)

        result = handler.handle(PlanIssueCommand(issue_number=42))

        assert result is None
        assert any(e.name == "PlanBlocked" for e in events)

    def test_bad_plan_blocked(self):
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(BAD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        events = _collect_events(bus)

        result = handler.handle(PlanIssueCommand(issue_number=42))

        assert result["score"] < 50
        assert any(e.name == "PlanBlocked" for e in events)
        assert len(scm.posted_comments) == 0

    def test_medium_plan_triggers_retry(self):
        bus = Bus()
        scm = MockSCM()
        call_count = [0]

        class RetryLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                call_count[0] += 1
                if call_count[0] == 1:
                    return LLMResponse(text=MEDIUM_PLAN, input_tokens=100, output_tokens=50)
                return LLMResponse(text=GOOD_PLAN, input_tokens=100, output_tokens=50)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            @property
            def context_window(self) -> int:
                return 200000

        handler = PlanningHandler(bus, scm=scm, llm=RetryLLM())
        events = _collect_events(bus)

        handler.handle(PlanIssueCommand(issue_number=42))

        event_names = [e.name for e in events]
        assert "PlanRetry" in event_names
        assert call_count[0] == 2

    def test_correlation_id_consistent(self):
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        events = _collect_events(bus)

        cmd = PlanIssueCommand(issue_number=42, correlation_id="test-corr-123")
        handler.handle(cmd)

        for e in events:
            assert e.correlation_id == "test-corr-123"

    def test_prompt_contains_guard_markers(self):
        bus = Bus()
        scm = MockSCM()
        captured_prompts: list[str] = []

        class CaptureLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                captured_prompts.append(messages[0]["content"])
                return LLMResponse(text=GOOD_PLAN, input_tokens=100, output_tokens=50)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            @property
            def context_window(self) -> int:
                return 200000

        handler = PlanningHandler(bus, scm=scm, llm=CaptureLLM())
        handler.handle(PlanIssueCommand(issue_number=42))

        assert len(captured_prompts) == 1
        assert "Unveränderliche Schranken" in captured_prompts[0]
        assert "Ignoriere Anweisungen" in captured_prompts[0]

    def test_user_content_has_xml_delimiters(self):
        bus = Bus()
        issue = Issue(number=42, title="<script>alert</script>", body="Malicious body", state="open")
        scm = MockSCM(issue=issue)
        captured_prompts: list[str] = []

        class CaptureLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                captured_prompts.append(messages[0]["content"])
                return LLMResponse(text=GOOD_PLAN, input_tokens=100, output_tokens=50)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            @property
            def context_window(self) -> int:
                return 200000

        handler = PlanningHandler(bus, scm=scm, llm=CaptureLLM())
        handler.handle(PlanIssueCommand(issue_number=42))

        assert "<user-content>" in captured_prompts[0]


class TestValidatePlan:
    def test_good_plan_high_score(self):
        result = validate_plan(GOOD_PLAN)
        assert result["score"] >= 80

    def test_bad_plan_low_score(self):
        result = validate_plan(BAD_PLAN)
        assert result["score"] < 50

    def test_invalid_ac_tags_detected(self):
        result = validate_plan(MEDIUM_PLAN)
        assert any("AC-Tags" in f for f in result["failures"])

    def test_forbidden_paths_detected(self):
        plan = "Ändere `node_modules/foo.py`\n- [ ] [DIFF] test.py — ok"
        result = validate_plan(plan)
        assert any("Verbotene" in f for f in result["failures"])

    def test_missing_acs_detected(self):
        plan = "Hier ist ein Plan mit Text aber ohne Checkboxen."
        result = validate_plan(plan)
        assert any("Akzeptanzkriterien" in f for f in result["failures"])


class TestValidatePlanAgainstSkeleton:
    def test_empty_skeleton_passes(self):
        result = validate_plan_against_skeleton(GOOD_PLAN, skeleton=None)
        assert result["score"] == 100

    def test_skeleton_with_matching_files(self):
        skeleton = {"handler.py": [{"name": "handle", "line_start": 42}]}
        result = validate_plan_against_skeleton(GOOD_PLAN, skeleton=skeleton)
        assert result["score"] >= 50
