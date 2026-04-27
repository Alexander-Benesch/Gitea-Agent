from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import (
    HealthCheckCommand,
    ImplementCommand,
    PlanIssueCommand,
    ScanIssuesCommand,
)

log = logging.getLogger(__name__)


class RestAPI:
    def __init__(
        self,
        bus: Bus,
        auth_middleware: Any | None = None,
        setup_handler: Any | None = None,
        dashboard_handler: Any | None = None,
    ) -> None:
        self._bus = bus
        self._auth = auth_middleware
        self._setup = setup_handler
        self._dashboard = dashboard_handler

    def handle_request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict[str, Any]:
        if self._auth and not self._auth.authenticate(headers or {}):
            return {"status": 401, "error": "unauthorized"}

        route = f"{method.upper()} {path}"

        if route == "POST /api/v1/setup/labels":
            if self._setup is None:
                return {"status": 503, "error": "setup handler not available"}
            result = self._setup.sync_labels()
            return {"status": 200, "data": result}

        if route == "POST /api/v1/settings/flag":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            name = (body or {}).get("name", "")
            enabled = (body or {}).get("enabled")
            if not name or enabled is None:
                return {"status": 400, "error": "name and enabled required"}
            result = self._dashboard.set_feature_flag(str(name), bool(enabled))
            if not result.get("updated"):
                return {"status": 400, "data": result}
            return {"status": 200, "data": result}

        if route.startswith("POST /api/v1/issues/") and route.endswith("/plan"):
            issue_id = self._extract_issue_id(path)
            if issue_id is None:
                return {"status": 400, "error": "invalid issue id"}
            result = self._bus.send(PlanIssueCommand(issue_number=issue_id))
            return {"status": 202, "data": result}

        if route.startswith("POST /api/v1/issues/") and route.endswith("/implement"):
            issue_id = self._extract_issue_id(path)
            if issue_id is None:
                return {"status": 400, "error": "invalid issue id"}
            result = self._bus.send(ImplementCommand(issue_number=issue_id))
            return {"status": 202, "data": result}

        if route == "GET /api/v1/health":
            result = self._bus.send(HealthCheckCommand())
            return {"status": 200, "data": result}

        if route == "GET /api/metrics":
            metrics = self._get_metrics()
            return {"status": 200, "data": metrics}

        if route == "POST /api/v1/scan":
            result = self._bus.send(ScanIssuesCommand())
            return {"status": 202, "data": result}

        return {"status": 404, "error": f"not found: {route}"}

    def _extract_issue_id(self, path: str) -> int | None:
        parts = path.strip("/").split("/")
        for i, part in enumerate(parts):
            if part == "issues" and i + 1 < len(parts):
                try:
                    return int(parts[i + 1])
                except ValueError:
                    return None
        return None

    def _get_metrics(self) -> dict[str, Any]:
        for mw in self._bus._middlewares:
            if hasattr(mw, "counts"):
                return {
                    "counts": dict(mw.counts),
                    "errors": dict(mw.errors),
                    "total_ms": {k: round(v, 2) for k, v in mw.total_ms.items()},
                }
        return {"counts": {}, "errors": {}, "total_ms": {}}
