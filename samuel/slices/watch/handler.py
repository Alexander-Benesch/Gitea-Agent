from __future__ import annotations

import logging
import threading
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import (
    Command,
    ScanIssuesCommand,
)
from samuel.core.events import IssueReady
from samuel.core.ports import IConfig, IVersionControl
from samuel.core.types import Issue

log = logging.getLogger(__name__)

LABEL_PLAN = "status:plan"
LABEL_APPROVED = "status:approved"
LABEL_WIP = "status:wip"
LABEL_DONE = "status:done"

VALID_TRANSITIONS: dict[str, set[str]] = {
    LABEL_PLAN: {LABEL_APPROVED, LABEL_DONE},
    LABEL_APPROVED: {LABEL_WIP, LABEL_DONE},
    LABEL_WIP: {LABEL_DONE},
}

STATUS_LABELS = {LABEL_PLAN, LABEL_APPROVED, LABEL_WIP, LABEL_DONE}


def _status_labels(issue: Issue) -> list[str]:
    return [l.name for l in issue.labels if l.name in STATUS_LABELS]


class WatchHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config: IConfig | None = None,
        max_parallel: int = 1,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._config = config
        self._semaphore = threading.Semaphore(max_parallel)
        self._max_parallel = max_parallel
        self._active: set[int] = set()
        self._lock = threading.Lock()

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ScanIssuesCommand)
        correlation_id = cmd.correlation_id or ""

        if self._config:
            try:
                self._config.reload()
                log.debug("Config hot-reloaded at cycle start")
            except Exception:
                log.warning("Config reload failed, using cached config")

        if not self._scm:
            log.warning("No SCM configured, watch cycle skipped")
            return {"dispatched": 0, "label_fixes": 0}

        label_fixes = self._check_label_consistency()

        issues = self._scm.list_issues(labels=[LABEL_APPROVED])

        dispatched = 0
        for issue in issues:
            if not self._try_acquire(issue.number):
                log.debug("Semaphore full, skipping issue #%d", issue.number)
                continue

            try:
                self._bus.publish(IssueReady(
                    payload={"issue": issue.number, "title": issue.title},
                    correlation_id=correlation_id,
                ))
                # WorkflowEngine reagiert auf IssueReady und dispatcht PlanIssue.
                # Kein direkter PlanIssueCommand-Send — verhindert Doppel-Dispatch.
                dispatched += 1
            finally:
                self._release(issue.number)

        return {"dispatched": dispatched, "label_fixes": label_fixes}

    def _try_acquire(self, issue_number: int) -> bool:
        with self._lock:
            if issue_number in self._active:
                return False
        acquired = self._semaphore.acquire(blocking=False)
        if acquired:
            with self._lock:
                self._active.add(issue_number)
        return acquired

    def _release(self, issue_number: int) -> None:
        with self._lock:
            self._active.discard(issue_number)
        self._semaphore.release()

    def _check_label_consistency(self) -> int:
        fixes = 0
        for label in [LABEL_PLAN, LABEL_APPROVED, LABEL_WIP]:
            try:
                issues = self._scm.list_issues(labels=[label])
            except Exception:
                log.warning("Failed to list issues for label %s", label)
                continue

            for issue in issues:
                status_list = _status_labels(issue)
                if len(status_list) > 1:
                    keep = max(status_list, key=lambda l: list(STATUS_LABELS).index(l))
                    for extra in status_list:
                        if extra != keep:
                            try:
                                self._scm.swap_label(issue.number, extra, keep)
                                fixes += 1
                                log.info(
                                    "Label fix: issue #%d removed %s (kept %s)",
                                    issue.number, extra, keep,
                                )
                            except Exception:
                                log.warning("Failed to fix label on issue #%d", issue.number)
        return fixes
