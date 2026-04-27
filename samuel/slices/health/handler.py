from __future__ import annotations

import logging
import sys
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, HealthCheckCommand
from samuel.core.events import StartupBlocked
from samuel.core.ports import IConfig, ILLMProvider, IVersionControl

log = logging.getLogger(__name__)


class HealthHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm
        self._config = config

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, HealthCheckCommand)
        correlation_id = cmd.correlation_id or ""

        checks: dict[str, dict[str, Any]] = {}

        checks["python"] = {
            "passed": True,
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }

        checks["config"] = {"passed": self._config is not None}

        checks["scm"] = {"passed": self._scm is not None}
        if self._scm:
            try:
                self._scm.list_issues(labels=[])
                checks["scm"]["reachable"] = True
            except Exception as exc:
                checks["scm"]["reachable"] = False
                checks["scm"]["error"] = str(exc)

        checks["llm"] = {"passed": self._llm is not None}

        all_passed = all(c["passed"] for c in checks.values())
        critical_passed = checks["config"]["passed"]

        if not critical_passed:
            self._bus.publish(StartupBlocked(
                payload={"reason": "critical health checks failed", "checks": checks},
                correlation_id=correlation_id,
            ))

        return {
            "healthy": all_passed,
            "critical": critical_passed,
            "checks": checks,
        }
