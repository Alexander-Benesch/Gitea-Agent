from __future__ import annotations

import logging
import time
from typing import Any

from samuel.core.bus import Bus
from samuel.core.ports import IConfig
from samuel.core.types import WorkflowCheckpoint

log = logging.getLogger(__name__)

DEFAULT_TOKEN_BUDGET = 500_000
DEFAULT_TIME_LIMIT = 3600


class SessionHandler:
    def __init__(
        self,
        bus: Bus,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._checkpoints: dict[int, WorkflowCheckpoint] = {}
        self._token_usage: int = 0
        self._start_time: float = time.monotonic()

    @property
    def _token_budget(self) -> int:
        if self._config:
            val = self._config.get("session.token_budget", DEFAULT_TOKEN_BUDGET)
            return int(val) if val else DEFAULT_TOKEN_BUDGET
        return DEFAULT_TOKEN_BUDGET

    @property
    def _time_limit(self) -> int:
        if self._config:
            val = self._config.get("session.time_limit", DEFAULT_TIME_LIMIT)
            return int(val) if val else DEFAULT_TIME_LIMIT
        return DEFAULT_TIME_LIMIT

    def track_tokens(self, tokens: int) -> None:
        self._token_usage += tokens

    def budget_remaining(self) -> int:
        return max(0, self._token_budget - self._token_usage)

    def time_remaining(self) -> float:
        elapsed = time.monotonic() - self._start_time
        return max(0.0, self._time_limit - elapsed)

    def is_within_budget(self) -> bool:
        return self._token_usage < self._token_budget

    def is_within_time(self) -> bool:
        return self.time_remaining() > 0

    def save_checkpoint(self, issue: int, phase: str, step: str, state: dict) -> None:
        self._checkpoints[issue] = WorkflowCheckpoint(
            issue=issue, phase=phase, step=step, state=state,
        )

    def get_checkpoint(self, issue: int) -> WorkflowCheckpoint | None:
        return self._checkpoints.get(issue)

    def clear_checkpoint(self, issue: int) -> None:
        self._checkpoints.pop(issue, None)

    def get_status(self) -> dict[str, Any]:
        return {
            "token_usage": self._token_usage,
            "token_budget": self._token_budget,
            "budget_remaining": self.budget_remaining(),
            "time_remaining": round(self.time_remaining(), 1),
            "checkpoints": list(self._checkpoints.keys()),
            "within_budget": self.is_within_budget(),
            "within_time": self.is_within_time(),
        }
