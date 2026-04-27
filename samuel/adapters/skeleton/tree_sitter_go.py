from __future__ import annotations

import logging
import re
from pathlib import Path

from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry

log = logging.getLogger(__name__)

_FUNC_RE = re.compile(r"^func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(", re.MULTILINE)
_STRUCT_RE = re.compile(r"^type\s+(\w+)\s+struct\s*\{", re.MULTILINE)
_INTERFACE_RE = re.compile(r"^type\s+(\w+)\s+interface\s*\{", re.MULTILINE)


class GoRegexBuilder(ISkeletonBuilder):
    """Regex-based Go skeleton builder.

    Uses tree-sitter-go if available, falls back to regex patterns.
    Regex covers the most common Go declarations reliably.
    """

    supported_extensions = {".go"}

    def extract(self, file: Path) -> list[SkeletonEntry]:
        source = file.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        entries: list[SkeletonEntry] = []

        for m in _FUNC_RE.finditer(source):
            name = m.group(3)
            receiver = m.group(2)
            line = source[:m.start()].count("\n") + 1
            end_line = self._find_block_end(lines, line - 1)
            kind = "method" if receiver else "function"
            display_name = f"{receiver}.{name}" if receiver else name
            entries.append(SkeletonEntry(
                name=display_name,
                kind=kind,
                file=str(file),
                line_start=line,
                line_end=end_line,
                language="go",
            ))

        for m in _STRUCT_RE.finditer(source):
            name = m.group(1)
            line = source[:m.start()].count("\n") + 1
            end_line = self._find_block_end(lines, line - 1)
            entries.append(SkeletonEntry(
                name=name,
                kind="struct",
                file=str(file),
                line_start=line,
                line_end=end_line,
                language="go",
            ))

        for m in _INTERFACE_RE.finditer(source):
            name = m.group(1)
            line = source[:m.start()].count("\n") + 1
            end_line = self._find_block_end(lines, line - 1)
            entries.append(SkeletonEntry(
                name=name,
                kind="interface",
                file=str(file),
                line_start=line,
                line_end=end_line,
                language="go",
            ))

        return entries

    @staticmethod
    def _find_block_end(lines: list[str], start: int) -> int:
        depth = 0
        for i in range(start, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start:
                return i + 1
        return len(lines)
