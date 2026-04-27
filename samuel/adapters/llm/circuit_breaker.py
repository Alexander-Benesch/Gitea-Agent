from __future__ import annotations

import logging
import time
from collections.abc import Callable

from samuel.core.errors import ProviderUnavailable
from samuel.core.events import ProviderCircuitOpen
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)

DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 120


class CircuitBreakerAdapter(ILLMProvider):
    def __init__(
        self,
        inner: ILLMProvider,
        on_event: Callable[[ProviderCircuitOpen], None] | None = None,
        *,
        failure_threshold: int | None = None,
        cooldown_seconds: int | None = None,
    ):
        self._inner = inner
        self._on_event = on_event
        self._failure_threshold = failure_threshold or DEFAULT_FAILURE_THRESHOLD
        self._cooldown_seconds = cooldown_seconds or DEFAULT_COOLDOWN_SECONDS
        self._state = "closed"
        self._failures = 0
        self._last_failure: float = 0

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    @property
    def state(self) -> str:
        return self._state

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        if self._state == "open":
            if time.monotonic() - self._last_failure >= self._cooldown_seconds:
                self._state = "half-open"
            else:
                raise ProviderUnavailable(
                    "llm", f"Circuit open, {self._cooldown_seconds}s cooldown"
                )

        try:
            resp = self._inner.complete(messages, **kwargs)
        except Exception:
            self._record_failure()
            raise

        if self._state == "half-open":
            self._state = "closed"
            self._failures = 0
        return resp

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)

    def _record_failure(self) -> None:
        self._failures += 1
        self._last_failure = time.monotonic()
        if self._failures >= self._failure_threshold:
            self._state = "open"
            log.warning("Circuit opened after %d failures", self._failures)
            if self._on_event:
                self._on_event(ProviderCircuitOpen(
                    payload={"failures": self._failures},
                    source="circuit_breaker",
                ))
