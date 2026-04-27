from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus

log = logging.getLogger(__name__)

DEFAULT_GLOBAL_CONSTRAINTS = [
    "Kein Slice importiert einen anderen Slice",
    "Externe Systeme nur über Ports (samuel.core.ports)",
    "Tests leben beim Slice: samuel/slices/*/tests/",
    "Aller Python-Code unter samuel/",
]

# Backwards-compat alias for older imports/tests
CONSTRAINTS = DEFAULT_GLOBAL_CONSTRAINTS


class ArchitectureHandler:
    def __init__(
        self,
        bus: Bus,
        project_root: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._bus = bus
        self._root = project_root or Path(".")
        self._arch_config_path = config_path or (self._root / "config" / "architecture.json")
        self._arch_data: dict[str, Any] = self._load_arch()

    def _load_arch(self) -> dict[str, Any]:
        if not self._arch_config_path.exists():
            return {}
        try:
            return json.loads(self._arch_config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load %s: %s", self._arch_config_path, exc)
            return {}

    def get_constraints(self) -> list[str]:
        globals_ = self._arch_data.get("global_constraints", [])
        return list(globals_) if globals_ else list(DEFAULT_GLOBAL_CONSTRAINTS)

    def get_constraints_for_files(self, files: list[str]) -> dict[str, Any]:
        """Liefert globale + module-spezifische Constraints für die gegebenen Dateien."""
        result: dict[str, Any] = {
            "global": self.get_constraints(),
            "modules": [],
        }
        for mod in self._arch_data.get("modules", []):
            mod_path = mod.get("path", "")
            if not mod_path:
                continue
            if self._matches_any(mod_path, files):
                result["modules"].append({
                    "path": mod_path,
                    "role": mod.get("role", ""),
                    "description": mod.get("description", ""),
                    "constraints": mod.get("constraints", []),
                })
        return result

    def get_expansion_scope(self, files: list[str]) -> dict[str, Any]:
        """Liefert erlaubte/blockierte Scope-Pfade basierend auf den Plan-Files."""
        allowed: set[str] = set()
        blocked: set[str] = set()
        roles: set[str] = set()

        modules = self._arch_data.get("modules", [])
        policy = self._arch_data.get("expansion_policy", {})

        for f in files:
            for mod in modules:
                mod_path = mod.get("path", "")
                if mod_path and self._path_matches(mod_path, f):
                    roles.add(mod.get("role", ""))

        for role in roles:
            p = policy.get(role, {})
            allowed.update(p.get("allowed_scopes", []))
            blocked.update(p.get("blocked_scopes", []))

        return {"allowed": allowed, "blocked": blocked, "roles": roles}

    @staticmethod
    def _path_matches(pattern: str, file_path: str) -> bool:
        if pattern.endswith("/"):
            return file_path.startswith(pattern)
        return file_path == pattern or file_path.startswith(pattern + "/")

    def _matches_any(self, pattern: str, files: list[str]) -> bool:
        return any(self._path_matches(pattern, f) for f in files)

    def validate_architecture(self) -> dict[str, Any]:
        violations: list[str] = []

        violations.extend(self._check_cross_slice_imports())
        violations.extend(self._check_test_location())

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "constraints_checked": len(CONSTRAINTS),
        }

    def _check_cross_slice_imports(self) -> list[str]:
        violations: list[str] = []
        slices_dir = self._root / "samuel" / "slices"
        if not slices_dir.exists():
            return violations

        for py_file in slices_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            parts = py_file.relative_to(slices_dir).parts
            if len(parts) < 2:
                continue
            current_slice = parts[0]

            try:
                content = py_file.read_text()
            except OSError:
                continue

            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith(("from samuel.slices.", "import samuel.slices.")):
                    match = re.match(r"(?:from|import)\s+samuel\.slices\.(\w+)", stripped)
                    if match and match.group(1) != current_slice:
                        violations.append(
                            f"{py_file.relative_to(self._root)}: cross-slice import of {match.group(1)}"
                        )
        return violations

    def _check_test_location(self) -> list[str]:
        violations: list[str] = []
        slices_dir = self._root / "samuel" / "slices"
        if not slices_dir.exists():
            return violations

        for slice_dir in slices_dir.iterdir():
            if not slice_dir.is_dir() or slice_dir.name.startswith(("_", ".")):
                continue
            test_dir = slice_dir / "tests"
            if not test_dir.exists():
                violations.append(f"missing tests/ directory in {slice_dir.name}")
        return violations
