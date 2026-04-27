from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.llm.circuit_breaker import (
    DEFAULT_COOLDOWN_SECONDS as COOLDOWN_SECONDS,
)
from samuel.adapters.llm.circuit_breaker import (
    DEFAULT_FAILURE_THRESHOLD as FAILURE_THRESHOLD,
)
from samuel.adapters.llm.circuit_breaker import (
    CircuitBreakerAdapter,
)
from samuel.core.errors import ProviderUnavailable
from samuel.core.events import ProviderCircuitOpen
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

MESSAGES = [{"role": "user", "content": "hi"}]
OK_RESPONSE = LLMResponse(text="ok", input_tokens=5, output_tokens=3)


def _make_inner(side_effect=None):
    inner = MagicMock(spec=ILLMProvider)
    inner.context_window = 200_000
    inner.capabilities = {"tool_use"}
    inner.estimate_tokens.return_value = 10
    if side_effect:
        inner.complete.side_effect = side_effect
    else:
        inner.complete.return_value = OK_RESPONSE
    return inner


class TestCircuitBreakerClosed:
    def test_passes_through(self):
        cb = CircuitBreakerAdapter(_make_inner())
        resp = cb.complete(MESSAGES)
        assert resp.text == "ok"
        assert cb.state == "closed"

    def test_delegates_properties(self):
        cb = CircuitBreakerAdapter(_make_inner())
        assert cb.context_window == 200_000
        assert cb.capabilities == {"tool_use"}
        assert cb.estimate_tokens("hello") == 10


class TestCircuitBreakerOpens:
    def test_opens_after_threshold(self):
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner)
        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert cb.state == "open"

    def test_rejects_when_open(self):
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner)
        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        with pytest.raises(ProviderUnavailable):
            cb.complete(MESSAGES)


class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open_after_cooldown(self):
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner)
        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert cb.state == "open"

        with patch("samuel.adapters.llm.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = cb._last_failure + COOLDOWN_SECONDS + 1
            inner.complete.side_effect = None
            inner.complete.return_value = OK_RESPONSE
            resp = cb.complete(MESSAGES)
        assert resp.text == "ok"
        assert cb.state == "closed"

    def test_half_open_failure_reopens(self):
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner)
        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)

        with patch("samuel.adapters.llm.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = cb._last_failure + COOLDOWN_SECONDS + 1
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert cb.state == "open"


class TestCircuitBreakerPartialFailure:
    def test_does_not_open_below_threshold(self):
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner)
        for _ in range(FAILURE_THRESHOLD - 1):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert cb.state == "closed"


class TestCircuitBreakerEvent:
    def test_publishes_event_on_open(self):
        events: list[ProviderCircuitOpen] = []
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner, on_event=events.append)
        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert len(events) == 1
        assert isinstance(events[0], ProviderCircuitOpen)
        assert events[0].payload["failures"] == FAILURE_THRESHOLD

    def test_no_event_without_callback(self):
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner)
        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert cb.state == "open"

    def test_no_event_below_threshold(self):
        events: list = []
        inner = _make_inner(side_effect=RuntimeError("fail"))
        cb = CircuitBreakerAdapter(inner, on_event=events.append)
        for _ in range(FAILURE_THRESHOLD - 1):
            with pytest.raises(RuntimeError):
                cb.complete(MESSAGES)
        assert len(events) == 0
