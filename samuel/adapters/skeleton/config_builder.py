from __future__ import annotations

import json
from pathlib import Path

from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry


class StructuredConfigBuilder(ISkeletonBuilder):
    supported_extensions = {".json", ".yaml", ".yml", ".toml"}

    def extract(self, file: Path) -> list[SkeletonEntry]:
        if file.suffix == ".json":
            return self._extract_json(file)
        if file.suffix in (".yaml", ".yml"):
            return self._extract_yaml(file)
        if file.suffix == ".toml":
            return self._extract_toml(file)
        return []

    def _extract_json(self, file: Path) -> list[SkeletonEntry]:
        try:
            source = file.read_text(encoding="utf-8")
            data = json.loads(source)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return []

        if not isinstance(data, dict):
            return []

        import re
        entries: list[SkeletonEntry] = []
        top_keys = set(data.keys())
        pattern = re.compile(r'"([^"\n]+)"\s*:')
        lines = source.splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.lstrip()
            indent_cols = len(line) - len(stripped)
            if indent_cols > 4:
                continue
            for m in pattern.finditer(line):
                key = m.group(1)
                if key in top_keys:
                    entries.append(SkeletonEntry(
                        name=key, kind="key", file=str(file),
                        line_start=i, line_end=i, language="json",
                    ))
                    top_keys.discard(key)
        return entries

    def _extract_yaml(self, file: Path) -> list[SkeletonEntry]:
        return self._extract_yaml_regex(file)

    def _extract_yaml_regex(self, file: Path) -> list[SkeletonEntry]:
        import re
        entries: list[SkeletonEntry] = []
        pattern = re.compile(r"^(\w[\w-]*):", re.MULTILINE)
        source = file.read_text(encoding="utf-8", errors="replace")
        for m in pattern.finditer(source):
            line = source[:m.start()].count("\n") + 1
            entries.append(SkeletonEntry(
                name=m.group(1),
                kind="key",
                file=str(file),
                line_start=line,
                line_end=line,
                language="yaml",
            ))
        return entries

    def _extract_toml(self, file: Path) -> list[SkeletonEntry]:
        import re
        entries: list[SkeletonEntry] = []
        source = file.read_text(encoding="utf-8", errors="replace")
        pattern = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)
        for m in pattern.finditer(source):
            line = source[:m.start()].count("\n") + 1
            entries.append(SkeletonEntry(
                name=m.group(1),
                kind="section",
                file=str(file),
                line_start=line,
                line_end=line,
                language="toml",
            ))
        return entries
