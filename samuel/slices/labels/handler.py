from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.events import Event
from samuel.core.ports import IVersionControl

log = logging.getLogger(__name__)

TRANSITIONS: dict[str, tuple[str, str]] = {
    "IssueReady":        ("",                "ready-for-agent"),
    "PlanCreated":       ("",                "status:plan"),
    "PlanValidated":     ("",                "status:approved"),
    "CodeGenerated":     ("ready-for-agent", "in-progress"),
    "PRCreated":         ("in-progress",     "needs-review"),
    "PlanBlocked":       ("",                "help wanted"),
    "GateFailed":        ("",                "help wanted"),
    "WorkflowBlocked":   ("",                "help wanted"),
}

STATUS_TRANSITIONS: dict[str, str] = {
    "CodeGenerated": "status:wip",
    "PRCreated":     "status:wip",
}

EVENT_NAMES = set(TRANSITIONS) | set(STATUS_TRANSITIONS)


class LabelsHandler:
    def __init__(self, bus: Bus, scm: IVersionControl | None = None) -> None:
        self._bus = bus
        self._scm = scm

    def register(self) -> None:
        for event_name in EVENT_NAMES:
            self._bus.subscribe(event_name, self._on_event)

    def _on_event(self, event: Event) -> None:
        if self._scm is None:
            return
        issue = self._extract_issue(event)
        if issue is None:
            return

        if event.name in TRANSITIONS:
            remove, add = TRANSITIONS[event.name]
            self._safe_swap(issue, remove, add)

        if event.name in STATUS_TRANSITIONS:
            self._safe_swap(issue, "", STATUS_TRANSITIONS[event.name])

    def _extract_issue(self, event: Event) -> int | None:
        payload: dict[str, Any] = event.payload or {}
        for key in ("issue", "issue_number"):
            val = payload.get(key)
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
        return None

    def _safe_swap(self, issue: int, remove: str, add: str) -> None:
        try:
            self._scm.swap_label(issue, remove, add)
        except Exception as exc:
            log.warning("Label transition failed (#%d, remove=%r, add=%r): %s",
                        issue, remove, add, exc)
