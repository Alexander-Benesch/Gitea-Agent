from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from samuel.core.ports import IQualityCheck

log = logging.getLogger(__name__)


class PythonSyntaxCheck(IQualityCheck):
    supported_extensions = {".py"}

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> dict[str, Any]:
        try:
            ast.parse(content, filename=str(file))
            return {"passed": True}
        except SyntaxError as e:
            return {
                "passed": False,
                "reason": f"SyntaxError at line {e.lineno}: {e.msg}",
                "line": e.lineno,
            }


class TreeSitterTypeScriptCheck(IQualityCheck):
    supported_extensions = {".ts", ".tsx", ".js", ".jsx"}

    def __init__(self) -> None:
        self._parser = None

    def _get_parser(self, extension: str) -> Any:
        if self._parser is not None:
            return self._parser
        try:
            import tree_sitter
            import tree_sitter_typescript

            if extension in (".ts", ".tsx"):
                lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            else:
                import tree_sitter_javascript
                lang = tree_sitter.Language(tree_sitter_javascript.language())

            parser = tree_sitter.Parser(lang)
            self._parser = parser
            return parser
        except ImportError:
            return None

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> dict[str, Any]:
        parser = self._get_parser(file.suffix)
        if parser is None:
            return {"passed": True, "skipped": True, "reason": "tree-sitter not available"}

        tree = parser.parse(content.encode("utf-8"))
        errors = []
        self._collect_errors(tree.root_node, errors)

        if errors:
            return {
                "passed": False,
                "reason": f"{len(errors)} syntax error(s)",
                "errors": errors[:10],
            }
        return {"passed": True}

    def _collect_errors(self, node: Any, errors: list[dict[str, Any]]) -> None:
        if node.type == "ERROR" or node.is_missing:
            errors.append({
                "line": node.start_point[0] + 1,
                "col": node.start_point[1],
                "type": "missing" if node.is_missing else "error",
            })
        for child in node.children:
            self._collect_errors(child, errors)


class ScopeGuard(IQualityCheck):
    supported_extensions = {"*"}

    _DANGEROUS_PATTERNS = [
        re.compile(r"\bos\.system\b"),
        re.compile(r"\bsubprocess\.call\b.*shell\s*=\s*True"),
        re.compile(r"\beval\s*\("),
        re.compile(r"\bexec\s*\("),
        re.compile(r"__import__\s*\("),
    ]

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        for i, line in enumerate(content.splitlines(), 1):
            for pattern in self._DANGEROUS_PATTERNS:
                if pattern.search(line):
                    violations.append({
                        "line": i,
                        "pattern": pattern.pattern,
                        "content": line.strip()[:100],
                    })

        if violations:
            return {
                "passed": False,
                "reason": f"{len(violations)} dangerous pattern(s) found",
                "violations": violations[:10],
            }
        return {"passed": True}


class DiffSizeCheck(IQualityCheck):
    supported_extensions = {"*"}

    MAX_LINES = 5000

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> dict[str, Any]:
        lines = content.count("\n") + 1
        if lines > self.MAX_LINES:
            return {
                "passed": False,
                "reason": f"File has {lines} lines (max {self.MAX_LINES})",
            }
        return {"passed": True}
