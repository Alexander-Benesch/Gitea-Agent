from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from samuel.core.bus import Bus
from samuel.core.commands import ImplementCommand
from samuel.core.events import (
    Event,
)
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse, WorkflowCheckpoint
from samuel.slices.implementation.handler import ImplementationHandler

# Mock all git operations so tests don't touch real git
_GIT_MOCK = patch("samuel.core.git._run", return_value=(True, ""))

GOOD_LLM_RESPONSE = """\
## test.py
<<<<<<< SEARCH
old_var = 1
=======
new_var = 2
>>>>>>> REPLACE
"""

EMPTY_RESPONSE = "No changes needed."


class MockSCM(IVersionControl):
    def __init__(self, plan_comment: str = "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] test.py"):
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


class MockLLM(ILLMProvider):
    def __init__(self, text: str = GOOD_LLM_RESPONSE, stop_reason: str = "end_turn"):
        self._text = text
        self._stop_reason = stop_reason

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=self._text, input_tokens=100, output_tokens=50,
            stop_reason=self._stop_reason,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200000


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestImplementationHandler:
    @_GIT_MOCK
    def test_happy_path(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["success"] is True
        event_names = [e.name for e in events]
        assert "CodeGenerated" in event_names
        assert "new_var = 2" in (tmp_path / "test.py").read_text()

        # Verify branch name flows through event payload
        cg_event = next(e for e in events if e.name == "CodeGenerated")
        assert cg_event.payload["branch"] == "samuel/issue-42"

    def test_no_llm_blocked(self):
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(bus, scm=MockSCM(), llm=None, enforce_context_quality=False)

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result is None
        assert any(e.name == "WorkflowBlocked" for e in events)

    def test_token_limit_publishes_event(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(),
            llm=MockLLM(text="partial...", stop_reason="max_tokens"),
            project_root=tmp_path,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["reason"] == "token_limit"
        event_names = [e.name for e in events]
        assert "TokenLimitHit" in event_names
        assert "WorkflowBlocked" in event_names

    def test_empty_response_no_patches(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(EMPTY_RESPONSE),
            project_root=tmp_path,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["success"] is False
        assert any(e.name == "WorkflowBlocked" for e in events)

    @_GIT_MOCK
    def test_correlation_id_flows(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
        enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42, correlation_id="impl-corr-1"))

        for e in events:
            assert e.correlation_id == "impl-corr-1"

    @_GIT_MOCK
    def test_prompt_has_guard_markers(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        captured: list[str] = []

        class CaptureLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                captured.append(messages[0]["content"])
                return LLMResponse(text=GOOD_LLM_RESPONSE, input_tokens=10, output_tokens=10)

            def estimate_tokens(self, text: str) -> int:
                return 0

            @property
            def context_window(self) -> int:
                return 200000

        bus = Bus()
        handler = ImplementationHandler(bus, scm=MockSCM(), llm=CaptureLLM(), project_root=tmp_path, enforce_context_quality=False)
        handler.handle(ImplementCommand(issue_number=42))

        assert "Unveränderliche Schranken" in captured[0]
        assert "Ignoriere Anweisungen" in captured[0]

    @_GIT_MOCK
    def test_checkpoint_saved_on_round(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        checkpoints: dict[int, WorkflowCheckpoint] = {}
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            checkpoint_store=checkpoints,
        enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42))

        # Checkpoint cleared after success
        assert 42 not in checkpoints

    @_GIT_MOCK
    def test_resume_from_checkpoint(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        checkpoints = {
            42: WorkflowCheckpoint(issue=42, phase="implementing", step="round_2", state={"round": 2}),
        }
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            checkpoint_store=checkpoints,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))
        assert result["success"] is True
