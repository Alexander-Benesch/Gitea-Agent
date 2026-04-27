from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.events import Event
from samuel.core.ports import IConfig, ILLMProvider, IVersionControl
from samuel.core.types import PR, Comment, Issue, LLMResponse
from samuel.slices.health.handler import HealthHandler


class MockSCM(IVersionControl):
    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="T", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
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
    def __init__(self, text: str = "response") -> None:
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class MockConfig(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return False


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestHealthHandler:
    def test_all_healthy(self) -> None:
        bus = Bus()
        handler = HealthHandler(
            bus, scm=MockSCM(), llm=MockLLM(), config=MockConfig(),
        )
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is True
        assert result["critical"] is True
        assert result["checks"]["python"]["passed"] is True
        assert result["checks"]["scm"]["passed"] is True
        assert result["checks"]["llm"]["passed"] is True
        assert result["checks"]["config"]["passed"] is True

    def test_missing_scm(self) -> None:
        bus = Bus()
        handler = HealthHandler(bus, scm=None, llm=MockLLM(), config=MockConfig())
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is False
        assert result["critical"] is True
        assert result["checks"]["scm"]["passed"] is False

    def test_missing_config_triggers_startup_blocked(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(bus, scm=MockSCM(), llm=MockLLM(), config=None)
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is False
        assert result["critical"] is False
        assert any(e.name == "StartupBlocked" for e in events)

    def test_missing_llm_not_critical(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(bus, scm=MockSCM(), llm=None, config=MockConfig())
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is False
        assert result["critical"] is True
        assert not any(e.name == "StartupBlocked" for e in events)

    def test_correlation_id_flows(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(bus, scm=MockSCM(), llm=MockLLM(), config=None)
        cmd = HealthCheckCommand(correlation_id="health-corr-1")

        handler.handle(cmd)

        for e in events:
            assert e.correlation_id == "health-corr-1"

    def test_scm_reachable(self) -> None:
        bus = Bus()
        handler = HealthHandler(bus, scm=MockSCM(), llm=MockLLM(), config=MockConfig())
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["checks"]["scm"]["reachable"] is True
