"""Tests for premium token limit handler."""
from __future__ import annotations

from samuel.core.bus import Bus
from samuel.core.events import WorkflowBlocked
from samuel.core.ports import IConfig
from samuel.premium.token_limit.handler import (
    DEFAULT_ISSUE_BUDGET,
    DEFAULT_SESSION_BUDGET,
    TokenLimitHandler,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockConfig(IConfig):
    def __init__(self, values: dict | None = None) -> None:
        self._v = values or {}

    def get(self, key: str, default=None):
        return self._v.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        pass


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTokenLimitHandler:
    """Tests for the TokenLimitHandler budget tracking."""

    def _make(self, config: MockConfig | None = None) -> tuple[TokenLimitHandler, Bus, list]:
        bus = Bus()
        events = _collect_events(bus)
        handler = TokenLimitHandler(bus, config=config)
        return handler, bus, events

    def test_check_budget_fresh_state_allowed(self):
        """A fresh handler should allow any request within budget."""
        handler, _, _ = self._make()

        result = handler.check_budget(issue_number=1, tokens_needed=100)

        assert result["allowed"] is True
        assert result["issue_used"] == 0
        assert result["session_used"] == 0
        assert result["issue_budget"] == DEFAULT_ISSUE_BUDGET
        assert result["session_budget"] == DEFAULT_SESSION_BUDGET

    def test_record_usage_tracks_per_issue_and_session(self):
        """record_usage should update both per-issue and session counters."""
        handler, _, _ = self._make()

        handler.record_usage(issue_number=1, tokens=500)
        handler.record_usage(issue_number=2, tokens=300)
        handler.record_usage(issue_number=1, tokens=200)

        budget1 = handler.check_budget(issue_number=1)
        budget2 = handler.check_budget(issue_number=2)

        assert budget1["issue_used"] == 700
        assert budget2["issue_used"] == 300
        assert budget1["session_used"] == 1000
        assert budget2["session_used"] == 1000

    def test_budget_exhaustion_blocks_issue_level(self):
        """When issue budget is exceeded, check_budget should deny."""
        config = MockConfig({"token_limit.per_issue": 1000, "token_limit.per_session": 999_999})
        handler, _, _ = self._make(config)

        handler.record_usage(issue_number=1, tokens=1000)
        result = handler.check_budget(issue_number=1, tokens_needed=1)

        assert result["allowed"] is False
        assert result["issue_remaining"] == 0

    def test_budget_exhaustion_blocks_session_level(self):
        """When session budget is exceeded, check_budget should deny."""
        config = MockConfig({"token_limit.per_issue": 999_999, "token_limit.per_session": 500})
        handler, _, _ = self._make(config)

        handler.record_usage(issue_number=1, tokens=500)
        result = handler.check_budget(issue_number=1, tokens_needed=1)

        assert result["allowed"] is False
        assert result["session_remaining"] == 0

    def test_block_if_exceeded_publishes_workflow_blocked(self):
        """block_if_exceeded should publish WorkflowBlocked when over budget."""
        config = MockConfig({"token_limit.per_issue": 100, "token_limit.per_session": 999_999})
        handler, bus, events = self._make(config)

        handler.record_usage(issue_number=42, tokens=101)
        blocked = handler.block_if_exceeded(issue_number=42, correlation_id="corr-123")

        assert blocked is True
        assert len(events) == 1
        assert isinstance(events[0], WorkflowBlocked)
        assert events[0].payload["issue"] == 42
        assert "token budget exhausted" in events[0].payload["reason"]
        assert events[0].correlation_id == "corr-123"

    def test_block_if_exceeded_returns_false_when_ok(self):
        """block_if_exceeded returns False and publishes nothing when within budget."""
        handler, bus, events = self._make()

        blocked = handler.block_if_exceeded(issue_number=1)

        assert blocked is False
        assert len(events) == 0

    def test_get_status_returns_correct_data(self):
        """get_status should return session totals and per-issue breakdown."""
        handler, _, _ = self._make()

        handler.record_usage(issue_number=1, tokens=100)
        handler.record_usage(issue_number=2, tokens=200)

        status = handler.get_status()

        assert status["session_used"] == 300
        assert status["session_budget"] == DEFAULT_SESSION_BUDGET
        assert status["issues_tracked"] == 2
        assert status["per_issue"] == {1: 100, 2: 200}

    def test_custom_budgets_from_config(self):
        """Config values should override default budgets."""
        config = MockConfig({
            "token_limit.per_issue": 5000,
            "token_limit.per_session": 20000,
        })
        handler, _, _ = self._make(config)

        result = handler.check_budget(issue_number=1)

        assert result["issue_budget"] == 5000
        assert result["session_budget"] == 20000
