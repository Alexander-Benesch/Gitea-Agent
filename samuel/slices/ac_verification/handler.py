from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, VerifyACCommand

log = logging.getLogger(__name__)

ACHandler = Callable[[str, Path | None], dict[str, Any]]

_AC_REGISTRY: dict[str, ACHandler] = {}

_SAFE_IMPORT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./ -]+$")


def register_ac_handler(tag: str, handler: ACHandler) -> None:
    _AC_REGISTRY[tag] = handler


def _sanitize_path(arg: str, project_root: Path) -> Path | None:
    cleaned = arg.strip().replace("..", "")
    if not _SAFE_PATH_RE.match(cleaned):
        return None
    resolved = (project_root / cleaned).resolve()
    if not str(resolved).startswith(str(project_root.resolve())):
        return None
    return resolved


def _check_diff(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    path = _sanitize_path(arg, project_root)
    if path is None:
        return {"passed": False, "reason": f"path rejected (traversal blocked): {arg}"}
    return {"passed": path.exists(), "reason": f"{'exists' if path.exists() else 'not found'}: {arg}"}


def _check_exists(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    path = _sanitize_path(arg, project_root)
    if path is None:
        return {"passed": False, "reason": f"path rejected (traversal blocked): {arg}"}
    return {"passed": path.exists(), "reason": f"{'exists' if path.exists() else 'not found'}: {arg}"}


def _check_import(arg: str, project_root: Path | None) -> dict[str, Any]:
    module_name = arg.strip()
    if not _SAFE_IMPORT_RE.match(module_name):
        return {"passed": False, "reason": f"import rejected (invalid chars): {arg}"}
    if any(dangerous in module_name for dangerous in ("os", "sys", "subprocess", "shutil", "pathlib")):
        return {"passed": False, "reason": f"import rejected (blocked module): {arg}"}
    try:
        importlib.import_module(module_name)
        return {"passed": True, "reason": f"importable: {module_name}"}
    except ImportError as exc:
        return {"passed": False, "reason": f"import failed: {exc}"}


def _check_grep(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    pattern = arg.strip().strip('"').strip("'")
    for py_file in project_root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            if pattern in py_file.read_text():
                return {"passed": True, "reason": f"found in {py_file.relative_to(project_root)}"}
        except OSError:
            continue
    return {"passed": False, "reason": f"pattern not found: {pattern}"}


def _check_grep_not(arg: str, project_root: Path | None) -> dict[str, Any]:
    result = _check_grep(arg, project_root)
    return {"passed": not result["passed"], "reason": result["reason"].replace("found", "still present") if result["passed"] else f"confirmed absent: {arg.strip()}"}


def _check_manual(arg: str, project_root: Path | None) -> dict[str, Any]:
    return {"passed": False, "reason": f"manual check required: {arg}", "manual": True}


register_ac_handler("DIFF", _check_diff)
register_ac_handler("EXISTS", _check_exists)
register_ac_handler("IMPORT", _check_import)
register_ac_handler("GREP", _check_grep)
register_ac_handler("GREP:NOT", _check_grep_not)
register_ac_handler("MANUAL", _check_manual)


AC_PATTERN = re.compile(r"- \[.\] \[([A-Z:]+)\]\s*(.+)")


class ACVerificationHandler:
    def __init__(
        self,
        bus: Bus,
        project_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._root = project_root

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, VerifyACCommand)

        plan_text = cmd.payload.get("plan_text", "")
        if not plan_text:
            return {"verified": False, "reason": "no plan text", "results": []}

        results: list[dict[str, Any]] = []
        for match in AC_PATTERN.finditer(plan_text):
            tag = match.group(1)
            arg = match.group(2).strip()
            handler = _AC_REGISTRY.get(tag)
            if handler:
                result = handler(arg, self._root)
                result["tag"] = tag
                result["arg"] = arg
                results.append(result)
            else:
                results.append({"tag": tag, "arg": arg, "passed": False, "reason": f"unknown tag: {tag}"})

        passed_count = sum(1 for r in results if r.get("passed"))
        manual_count = sum(1 for r in results if r.get("manual"))
        auto_total = len(results) - manual_count
        auto_passed = sum(1 for r in results if r.get("passed") and not r.get("manual"))

        return {
            "verified": auto_passed == auto_total and auto_total > 0,
            "total": len(results),
            "passed": passed_count,
            "manual": manual_count,
            "results": results,
        }
