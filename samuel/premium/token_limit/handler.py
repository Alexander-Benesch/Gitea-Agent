from __future__ import annotations

import logging
import threading
from typing import Any

from samuel.core.bus import Bus
from samuel.core.events import WorkflowBlocked
from samuel.core.ports import IConfig

log = logging.getLogger(__name__)

DEFAULT_ISSUE_BUDGET = 100_000
DEFAULT_SESSION_BUDGET = 500_000


class TokenLimitHandler:
    def __init__(
        self,
        bus: Bus,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._lock = threading.Lock()
        self._issue_usage: dict[int, int] = {}
        self._session_usage: int = 0

    @property
    def _issue_budget(self) -> int:
        if self._config:
            val = self._config.get("token_limit.per_issue", DEFAULT_ISSUE_BUDGET)
            return int(val) if val else DEFAULT_ISSUE_BUDGET
        return DEFAULT_ISSUE_BUDGET

    @property
    def _session_budget(self) -> int:
        if self._config:
            val = self._config.get("token_limit.per_session", DEFAULT_SESSION_BUDGET)
            return int(val) if val else DEFAULT_SESSION_BUDGET
        return DEFAULT_SESSION_BUDGET

    def check_budget(self, issue_number: int, tokens_needed: int = 0) -> dict[str, Any]:
        with self._lock:
            issue_used = self._issue_usage.get(issue_number, 0)

        issue_remaining = max(0, self._issue_budget - issue_used)
        session_remaining = max(0, self._session_budget - self._session_usage)

        issue_ok = issue_used + tokens_needed <= self._issue_budget
        session_ok = self._session_usage + tokens_needed <= self._session_budget

        return {
            "allowed": issue_ok and session_ok,
            "issue_used": issue_used,
            "issue_budget": self._issue_budget,
            "issue_remaining": issue_remaining,
            "session_used": self._session_usage,
            "session_budget": self._session_budget,
            "session_remaining": session_remaining,
        }

    def record_usage(self, issue_number: int, tokens: int) -> None:
        with self._lock:
            self._issue_usage[issue_number] = self._issue_usage.get(issue_number, 0) + tokens
            self._session_usage += tokens

    def block_if_exceeded(self, issue_number: int, correlation_id: str = "") -> bool:
        budget = self.check_budget(issue_number)
        if not budget["allowed"]:
            reason = "issue" if budget["issue_remaining"] == 0 else "session"
            self._bus.publish(WorkflowBlocked(
                payload={
                    "issue": issue_number,
                    "reason": f"token budget exhausted ({reason})",
                    "budget": budget,
                },
                correlation_id=correlation_id,
            ))
            return True
        return False

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_used": self._session_usage,
                "session_budget": self._session_budget,
                "issues_tracked": len(self._issue_usage),
                "per_issue": dict(self._issue_usage),
            }
