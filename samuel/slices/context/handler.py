from __future__ import annotations

import hashlib
import hmac
import logging
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import BuildContextCommand, Command
from samuel.core.ports import IConfig, ISkeletonBuilder

log = logging.getLogger(__name__)


class ContextHandler:
    def __init__(
        self,
        bus: Bus,
        project_root: Path | None = None,
        skeleton_builders: list[ISkeletonBuilder] | None = None,
        hmac_key: str = "",
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._root = project_root or Path(".")
        self._builders = skeleton_builders or []
        self._hmac_key = hmac_key
        self._max_file_size_kb: int = int(
            config.get("agent.context.max_file_size_kb", 50) if config else 50
        )
        self._max_skeleton_file_size_kb: int = int(
            config.get("agent.context.max_skeleton_file_size_kb", 20) if config else 20
        )
        _exclude_dirs = (
            config.get("agent.context.exclude_dirs", []) if config else []
        )
        self._exclude_dirs: set[str] = set(_exclude_dirs) if _exclude_dirs else {
            "__pycache__", ".git", ".venv", "venv", "node_modules",
        }
        _exclude_files = (
            config.get("agent.context.exclude_files", []) if config else []
        )
        self._exclude_files: set[str] = set(_exclude_files) if _exclude_files else set()
        _kw_ext = (
            config.get("agent.context.keyword_extensions", []) if config else []
        )
        self._keyword_extensions: set[str] = set(_kw_ext) if _kw_ext else {
            ".py", ".js", ".ts", ".go", ".java", ".rs", ".rb",
        }

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, BuildContextCommand)

        target_file = cmd.payload.get("file", "")
        start_line = cmd.payload.get("start", 0)
        end_line = cmd.payload.get("end", 0)

        if target_file and start_line and end_line:
            return self._get_slice(target_file, start_line, end_line)

        return self._build_skeleton()

    def _is_excluded(self, path: Path) -> bool:
        for part in path.parts:
            if part in self._exclude_dirs:
                return True
        return path.name in self._exclude_files

    def _build_skeleton(self) -> dict[str, Any]:
        max_bytes = self._max_skeleton_file_size_kb * 1024
        skeleton: dict[str, list[dict]] = {}
        for builder in self._builders:
            for f in self._root.rglob("*"):
                if self._is_excluded(f.relative_to(self._root)):
                    continue
                if f.suffix not in builder.supported_extensions:
                    continue
                if f.is_file() and f.stat().st_size > max_bytes:
                    continue
                try:
                    entries = builder.extract(f)
                    rel = str(f.relative_to(self._root))
                    skeleton[rel] = [
                        {"name": e.name, "kind": e.kind, "line_start": e.line_start, "line_end": e.line_end}
                        for e in entries
                    ]
                except Exception:
                    log.warning("Skeleton extraction failed for %s", f)
        return {"files": len(skeleton), "skeleton": skeleton}

    def _get_slice(self, file: str, start: int, end: int) -> dict[str, Any]:
        path = self._root / file
        if not path.exists():
            return {"error": f"file not found: {file}"}

        max_bytes = self._max_file_size_kb * 1024
        if path.stat().st_size > max_bytes:
            return {"error": f"file exceeds max_file_size_kb ({self._max_file_size_kb} KB): {file}"}

        lines = path.read_text().splitlines()
        start_idx = max(0, start - 1)
        end_idx = min(len(lines), end)
        content = "\n".join(lines[start_idx:end_idx])

        result: dict[str, Any] = {
            "file": file,
            "start": start,
            "end": end,
            "content": content,
            "line_count": end_idx - start_idx,
        }

        if self._hmac_key:
            sig = hmac.new(
                self._hmac_key.encode(),
                f"{file}:{start}:{end}".encode(),
                hashlib.sha256,
            ).hexdigest()[:16]
            result["signature"] = sig

        return result
