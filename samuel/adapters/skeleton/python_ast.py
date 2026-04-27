from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry


class PythonASTBuilder(ISkeletonBuilder):
    supported_extensions = {".py"}

    def extract(self, file: Path) -> list[SkeletonEntry]:
        source = file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(file))
        except SyntaxError:
            return []

        entries: list[SkeletonEntry] = []
        calls_map: dict[str, list[str]] = defaultdict(list)

        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        entries.append(
                            SkeletonEntry(
                                name=target.id,
                                kind="variable",
                                file=str(file),
                                line_start=node.lineno,
                                line_end=node.end_lineno or node.lineno,
                                language="python",
                            )
                        )
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                entries.append(
                    SkeletonEntry(
                        name=node.target.id,
                        kind="variable",
                        file=str(file),
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        language="python",
                    )
                )

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "function"
                calls = self._extract_calls(node)
                calls_map[node.name] = calls
                entries.append(
                    SkeletonEntry(
                        name=node.name,
                        kind=kind,
                        file=str(file),
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        calls=calls,
                        called_by=[],
                        language="python",
                    )
                )
            elif isinstance(node, ast.ClassDef):
                entries.append(
                    SkeletonEntry(
                        name=node.name,
                        kind="class",
                        file=str(file),
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        calls=[],
                        called_by=[],
                        language="python",
                    )
                )

        entry_names = {e.name for e in entries}
        for entry in entries:
            for caller_name, caller_calls in calls_map.items():
                if entry.name in caller_calls and caller_name != entry.name:
                    if caller_name in entry_names:
                        entry.called_by.append(caller_name)

        return entries

    def _extract_calls(self, node: ast.AST) -> list[str]:
        calls: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return sorted(set(calls))
