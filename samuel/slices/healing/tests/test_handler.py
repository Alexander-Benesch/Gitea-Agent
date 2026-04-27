from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealCommand
from samuel.core.events import Event
from samuel.core.ports import IConfig, ILLMProvider
from samuel.core.types import LLMResponse
from samuel.slices.healing.handler import HealingHandler


class MockLLM(ILLMProvider):
    def __init__(self, text: str = "fix suggestion") -> None:
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class MockConfig(IConfig):
    def __init__(self, flags: dict[str, bool] | None = None, values: dict[str, Any] | None = None):
        self._flags = flags or {}
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return self._flags.get(name, False)

    def reload(self) -> None:
        pass


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestHealingHandler:
    def test_disabled_by_default(self):
        bus = Bus()
        handler = HealingHandler(bus, config=MockConfig())
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "disabled"

    def test_heals_when_enabled(self):
        bus = Bus()
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is True
        assert result["failure_type"] == "eval"
        assert "suggestion" in result

    def test_budget_exhausted_after_max_attempts(self):
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(
            flags={"healing": True},
            values={"healing.max_attempts": 2},
        )
        handler = HealingHandler(bus, llm=MockLLM(), config=config)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 3},
        ))
        assert result["healed"] is False
        assert result["reason"] == "budget_exhausted"
        assert any(e.name == "WorkflowBlocked" for e in events)

    def test_token_budget_exhausted(self):
        bus = Bus()
        _collect_events(bus)
        config = MockConfig(
            flags={"healing": True},
            values={"healing.max_tokens": 100},
        )
        handler = HealingHandler(bus, llm=MockLLM(), config=config)
        handler._token_budget_used[42] = 200
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "token_budget_exhausted"

    def test_no_llm_blocks(self):
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=None, config=config)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "no_llm"
        assert any(e.name == "WorkflowBlocked" for e in events)

    def test_token_tracking_accumulates(self):
        bus = Bus()
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 2},
        ))

        assert handler._token_budget_used[42] == 300

    def test_no_config_means_disabled(self):
        bus = Bus()
        handler = HealingHandler(bus, llm=MockLLM(), config=None)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "disabled"
