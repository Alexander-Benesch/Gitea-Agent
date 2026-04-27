from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus

log = logging.getLogger(__name__)


class CodeAnalysisHandler:
    def __init__(
        self,
        bus: Bus,
        project_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._root = project_root or Path(".")

    def run_checks(self, files: list[str] | None = None) -> dict[str, Any]:
        results: dict[str, Any] = {}

        results["syntax"] = self._check_syntax(files)
        results["imports"] = self._check_imports(files)

        all_passed = all(r.get("passed", False) for r in results.values())
        return {"passed": all_passed, "checks": results}

    def _check_syntax(self, files: list[str] | None = None) -> dict[str, Any]:
        targets = files or self._find_python_files()
        errors: list[str] = []
        for f in targets:
            path = self._root / f if not Path(f).is_absolute() else Path(f)
            if not path.exists():
                continue
            try:
                compile(path.read_text(), str(path), "exec")
            except SyntaxError as exc:
                errors.append(f"{f}:{exc.lineno}: {exc.msg}")
        return {"passed": len(errors) == 0, "errors": errors}

    def _check_imports(self, files: list[str] | None = None) -> dict[str, Any]:
        targets = files or self._find_python_files()
        cross_slice: list[str] = []
        for f in targets:
            path = self._root / f if not Path(f).is_absolute() else Path(f)
            if not path.exists() or "slices" not in str(path):
                continue
            try:
                content = path.read_text()
            except OSError:
                continue
            for line in content.splitlines():
                if line.strip().startswith(("from samuel.slices.", "import samuel.slices.")):
                    match = re.match(r"(?:from|import)\s+samuel\.slices\.(\w+)", line.strip())
                    if match:
                        importing_slice = str(path).split("slices/")[1].split("/")[0]
                        imported_slice = match.group(1)
                        if imported_slice != importing_slice:
                            cross_slice.append(f"{f}: imports samuel.slices.{imported_slice}")
        return {"passed": len(cross_slice) == 0, "violations": cross_slice}

    def _find_python_files(self) -> list[str]:
        return [
            str(p.relative_to(self._root))
            for p in self._root.rglob("*.py")
            if "__pycache__" not in str(p)
        ]
