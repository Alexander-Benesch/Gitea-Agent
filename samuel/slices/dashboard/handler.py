from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.ports import IConfig, IVersionControl
from samuel.slices.dashboard.data import (
    KNOWN_FEATURE_FLAGS,
    get_branches,
    get_feature_flags,
    get_llm_routing,
    get_llm_usage,
    get_log_entries,
    get_security_overview,
    get_tamper_events,
    get_workflow_issues,
)

log = logging.getLogger(__name__)


class DashboardHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config: IConfig | None = None,
        transfer_warning_fn: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._config = config
        self._transfer_warning_fn = transfer_warning_fn

    def get_transfer_warnings(self) -> list[dict[str, Any]]:
        if self._transfer_warning_fn:
            return self._transfer_warning_fn()
        return []

    def get_status(self) -> dict[str, Any]:
        metrics = self._get_metrics()
        transfer_warnings = self.get_transfer_warnings()
        warnings = [w for w in transfer_warnings if w.get("warning")]
        mode = self._config.get("agent.mode", "standard") if self._config else "standard"
        self_mode = bool(self._config.get("agent.self_mode", False)) if self._config else False
        return {
            "mode": mode,
            "self_mode": self_mode,
            "scm_connected": self._scm is not None,
            "metrics": metrics,
            "transfer_warnings": warnings,
        }

    def get_health(self) -> dict[str, Any]:
        checks: dict[str, bool] = {
            "scm": self._scm is not None,
            "config": self._config is not None,
        }
        healthy = all(checks.values())
        return {"healthy": healthy, "checks": checks}

    def get_metrics(self) -> dict[str, Any]:
        return self._get_metrics()

    def _get_metrics(self) -> dict[str, Any]:
        for mw in self._bus._middlewares:
            if hasattr(mw, "counts"):
                return {
                    "counts": dict(mw.counts),
                    "errors": dict(mw.errors),
                    "total_ms": {k: round(v, 2) for k, v in mw.total_ms.items()},
                }
        return {"counts": {}, "errors": {}, "total_ms": {}}

    def get_logs(self) -> list[dict]:
        """Return formatted audit log entries."""
        return get_log_entries()

    def get_security(self) -> dict[str, Any]:
        """Return OWASP Agentic AI risk overview plus tamper alerts."""
        overview = get_security_overview()
        overview["tamper_events"] = get_tamper_events()
        return overview

    def get_workflow(self) -> dict[str, Any]:
        """Return workflow issues and branch overview."""
        return {
            "issues": get_workflow_issues(),
            "branches": get_branches(),
        }

    def get_llm(self) -> dict[str, Any]:
        """Return LLM token usage, cost statistics, and routing."""
        usage = get_llm_usage()
        usage["routing"] = get_llm_routing(self._config)
        return usage

    def get_settings(self) -> dict[str, Any]:
        """Return feature flags and current settings."""
        return {"flags": get_feature_flags(self._config)}

    def set_feature_flag(self, name: str, enabled: bool) -> dict[str, Any]:
        """Toggle a feature flag via in-memory config override.

        Override is NOT persisted to disk — it lasts for the process lifetime.
        """
        known_keys = {k for k, _, _ in KNOWN_FEATURE_FLAGS}
        if name not in known_keys:
            return {"updated": False, "error": f"unknown flag: {name}"}
        if self._config is None:
            return {"updated": False, "error": "config not available"}
        overrides = getattr(self._config, "_overrides", None)
        if overrides is None or not isinstance(overrides, dict):
            return {"updated": False, "error": "config does not support overrides"}
        overrides[f"features.{name}"] = bool(enabled)
        return {"updated": True, "name": name, "enabled": bool(enabled)}

    def get_self_check(self) -> dict[str, Any]:
        """Run HealthCheckCommand and return structured checks list.

        Each check: name, status (OK/FAIL), time (empty if not provided),
        detail (version / error / extra info). Also includes the agent mode.
        """
        result = self._bus.send(HealthCheckCommand(payload={})) or {}
        raw_checks = result.get("checks", {}) if isinstance(result, dict) else {}
        checks: list[dict[str, Any]] = []
        for name, val in raw_checks.items():
            if isinstance(val, dict):
                passed = bool(val.get("passed", False))
                detail_bits: list[str] = []
                for k, v in val.items():
                    if k == "passed":
                        continue
                    detail_bits.append(f"{k}={v}")
                detail = ", ".join(detail_bits)
            else:
                passed = bool(val)
                detail = ""
            checks.append({
                "name": name,
                "status": "OK" if passed else "FAIL",
                "time": "",
                "detail": detail,
            })
        mode = self._config.get("agent.mode", "standard") if self._config else "standard"
        self_mode = bool(self._config.get("agent.self_mode", False)) if self._config else False
        return {
            "mode": "self" if self_mode else mode,
            "healthy": bool(result.get("healthy", False)) if isinstance(result, dict) else False,
            "checks": checks,
        }

    def get_api_data(self, endpoint: str) -> dict[str, Any]:
        if endpoint == "status":
            return self.get_status()
        if endpoint == "health":
            return self.get_health()
        if endpoint == "metrics":
            return self.get_metrics()
        if endpoint == "transfer_warnings":
            return {"transfer_warnings": self.get_transfer_warnings()}
        if endpoint == "logs":
            return self.get_logs()
        if endpoint == "security":
            return self.get_security()
        if endpoint == "workflow":
            return self.get_workflow()
        if endpoint == "llm":
            return self.get_llm()
        if endpoint == "settings":
            return self.get_settings()
        if endpoint == "self_check":
            return self.get_self_check()
        return {"error": f"unknown endpoint: {endpoint}"}
