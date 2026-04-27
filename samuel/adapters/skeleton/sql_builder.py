from __future__ import annotations

import re
from pathlib import Path

from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)
_CREATE_VIEW_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)
_CREATE_PROC_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)
_CREATE_TRIGGER_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)


class SQLBuilder(ISkeletonBuilder):
    supported_extensions = {".sql"}

    def extract(self, file: Path) -> list[SkeletonEntry]:
        source = file.read_text(encoding="utf-8", errors="replace")
        entries: list[SkeletonEntry] = []

        patterns = [
            (_CREATE_TABLE_RE, "table"),
            (_CREATE_VIEW_RE, "view"),
            (_CREATE_PROC_RE, "procedure"),
            (_CREATE_INDEX_RE, "index"),
            (_CREATE_TRIGGER_RE, "trigger"),
        ]

        for pattern, kind in patterns:
            for m in pattern.finditer(source):
                line = source[:m.start()].count("\n") + 1
                entries.append(SkeletonEntry(
                    name=m.group(1),
                    kind=kind,
                    file=str(file),
                    line_start=line,
                    line_end=line,
                    language="sql",
                ))

        return entries
