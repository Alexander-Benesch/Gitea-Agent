from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.ports import IConfig
from samuel.slices.session.handler import (
    DEFAULT_TOKEN_BUDGET,
    SessionHandler,
)


class MockConfig(IConfig):
    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self._data = overrides or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False


class TestSessionHandler:
    def test_default_budget(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)

        assert handler.budget_remaining() == DEFAULT_TOKEN_BUDGET
        assert handler.is_within_budget() is True

    def test_track_tokens_reduces_budget(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)
        handler.track_tokens(1000)

        assert handler.budget_remaining() == DEFAULT_TOKEN_BUDGET - 1000
        assert handler.is_within_budget() is True

    def test_budget_exhausted(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)
        handler.track_tokens(DEFAULT_TOKEN_BUDGET + 1)

        assert handler.budget_remaining() == 0
        assert handler.is_within_budget() is False

    def test_custom_budget_from_config(self) -> None:
        bus = Bus()
        config = MockConfig({"session.token_budget": 100})
        handler = SessionHandler(bus, config=config)

        assert handler.budget_remaining() == 100

    def test_time_remaining_positive(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)

        assert handler.time_remaining() > 0
        assert handler.is_within_time() is True

    def test_checkpoint_save_and_get(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)
        handler.save_checkpoint(issue=42, phase="plan", step="validate", state={"draft": True})

        cp = handler.get_checkpoint(42)

        assert cp is not None
        assert cp.issue == 42
        assert cp.phase == "plan"
        assert cp.step == "validate"
        assert cp.state == {"draft": True}

    def test_checkpoint_get_missing(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)

        assert handler.get_checkpoint(99) is None

    def test_checkpoint_clear(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)
        handler.save_checkpoint(issue=10, phase="impl", step="code", state={})

        handler.clear_checkpoint(10)

        assert handler.get_checkpoint(10) is None

    def test_clear_nonexistent_checkpoint_no_error(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)
        handler.clear_checkpoint(999)  # should not raise

    def test_get_status(self) -> None:
        bus = Bus()
        handler = SessionHandler(bus)
        handler.track_tokens(200)
        handler.save_checkpoint(issue=1, phase="p", step="s", state={})

        status = handler.get_status()

        assert status["token_usage"] == 200
        assert status["token_budget"] == DEFAULT_TOKEN_BUDGET
        assert status["budget_remaining"] == DEFAULT_TOKEN_BUDGET - 200
        assert status["within_budget"] is True
        assert status["within_time"] is True
        assert 1 in status["checkpoints"]
