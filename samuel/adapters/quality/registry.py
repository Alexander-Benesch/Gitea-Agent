from __future__ import annotations

import json
import logging
from pathlib import Path

from samuel.core.ports import IQualityCheck

log = logging.getLogger(__name__)


QUALITY_CHECKS: dict[str, list[IQualityCheck]] = {}


def register_check(check: IQualityCheck, *, extension: str | None = None) -> None:
    if extension is not None:
        QUALITY_CHECKS.setdefault(extension, []).append(check)
    else:
        for ext in check.supported_extensions:
            QUALITY_CHECKS.setdefault(ext, []).append(check)


def get_checks_for(extension: str) -> list[IQualityCheck]:
    specific = QUALITY_CHECKS.get(extension, [])
    if extension == "*":
        return list(specific)
    wildcard = QUALITY_CHECKS.get("*", [])
    return specific + wildcard


def load_registry_from_config(config_path: Path | None = None) -> None:
    from samuel.adapters.quality.checks import (
        DiffSizeCheck,
        PythonSyntaxCheck,
        ScopeGuard,
        TreeSitterTypeScriptCheck,
    )

    defaults: dict[str, list[IQualityCheck]] = {
        ".py": [PythonSyntaxCheck()],
        ".ts": [TreeSitterTypeScriptCheck()],
        ".tsx": [TreeSitterTypeScriptCheck()],
        ".js": [TreeSitterTypeScriptCheck()],
        "*": [DiffSizeCheck(), ScopeGuard()],
    }

    if config_path and config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            overrides = data.get("quality_checks", {})
            if overrides.get("disabled"):
                for ext in overrides["disabled"]:
                    defaults.pop(ext, None)
            log.info("Loaded quality config from %s", config_path)
        except (json.JSONDecodeError, KeyError):
            log.warning("Invalid quality config, using defaults")

    QUALITY_CHECKS.clear()
    for ext, checks in defaults.items():
        for check in checks:
            register_check(check, extension=ext)

    total = sum(len(v) for v in QUALITY_CHECKS.values())
    log.info("Quality registry: %d checks across %d extensions", total, len(QUALITY_CHECKS))
