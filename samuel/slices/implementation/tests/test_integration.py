from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import AuditMiddleware, Bus, ErrorMiddleware
from samuel.core.commands import ImplementCommand
from samuel.core.events import (
    Event,
)
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse
from samuel.slices.implementation.handler import ImplementationHandler

GOOD_RESPONSE = """\
## test.py
<<<<<<< SEARCH
old_var = 1
=======
new_var = 2
>>>>>>> REPLACE
"""


class FakeSCM(IVersionControl):
    def get_issue(self, number: int) -> Issue:
        return Issue(
            number=number,
            title="Test feature implementation",
            body="Implement the feature described in the plan comment with sufficient detail.",
            state="open",
        )

    def get_comments(self, number: int) -> list[Comment]:
        return [Comment(id=1, body="## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] test.py", user="bot")]

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


class FakeLLM(ILLMProvider):
    def __init__(self, text: str = GOOD_RESPONSE, stop_reason: str = "end_turn"):
        self._text = text
        self._stop = stop_reason

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50, stop_reason=self._stop)

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


class TestE2EHappyPath:
    def test_implement_command_to_code_generated(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        audit = AuditSink()
        bus.add_middleware(AuditMiddleware(sink=audit))
        bus.add_middleware(ErrorMiddleware())

        handler = ImplementationHandler(bus, scm=FakeSCM(), llm=FakeLLM(), project_root=tmp_path, enforce_context_quality=False)
        bus.register_command("Implement", handler.handle)

        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        result = bus.send(ImplementCommand(issue_number=42))

        assert result["success"] is True
        event_names = [e.name for e in events]
        assert "CodeGenerated" in event_names
        assert "new_var = 2" in (tmp_path / "test.py").read_text()

        audit_names = [e.payload.get("message_name") for e in audit.entries]
        assert "CodeGenerated" in audit_names

    def test_correlation_id_consistent(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        handler = ImplementationHandler(bus, scm=FakeSCM(), llm=FakeLLM(), project_root=tmp_path, enforce_context_quality=False)
        bus.register_command("Implement", handler.handle)

        bus.send(ImplementCommand(issue_number=42, correlation_id="e2e-corr"))

        for e in events:
            assert e.correlation_id == "e2e-corr"


class TestE2ETokenLimit:
    def test_token_limit_rollback(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("original\n")
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        handler = ImplementationHandler(
            bus, scm=FakeSCM(),
            llm=FakeLLM(text="partial...", stop_reason="max_tokens"),
            project_root=tmp_path,
            enforce_context_quality=False,
        )
        bus.register_command("Implement", handler.handle)

        result = bus.send(ImplementCommand(issue_number=42))

        assert result["reason"] == "token_limit"
        event_names = [e.name for e in events]
        assert "TokenLimitHit" in event_names
        assert "WorkflowBlocked" in event_names
        assert (tmp_path / "test.py").read_text() == "original\n"


class TestE2EBadPatches:
    def test_no_patches_workflow_blocked(self, tmp_path: Path):
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        handler = ImplementationHandler(
            bus, scm=FakeSCM(), llm=FakeLLM("just text no patches"),
            project_root=tmp_path,
            enforce_context_quality=False,
        )
        bus.register_command("Implement", handler.handle)

        result = bus.send(ImplementCommand(issue_number=42))

        assert result["success"] is False
        assert any(e.name == "WorkflowBlocked" for e in events)
