from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry

log = logging.getLogger(__name__)


class TreeSitterTSBuilder(ISkeletonBuilder):
    supported_extensions = {".ts", ".tsx", ".js", ".jsx"}

    def __init__(self) -> None:
        self._parser = None

    def _get_parser(self, extension: str) -> Any:
        if self._parser is not None:
            return self._parser
        try:
            import tree_sitter

            if extension in (".ts", ".tsx"):
                import tree_sitter_typescript
                lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            else:
                import tree_sitter_javascript
                lang = tree_sitter.Language(tree_sitter_javascript.language())

            self._parser = tree_sitter.Parser(lang)
            return self._parser
        except ImportError:
            log.warning("tree-sitter not available for %s", extension)
            return None

    def extract(self, file: Path) -> list[SkeletonEntry]:
        parser = self._get_parser(file.suffix)
        if parser is None:
            return []

        source = file.read_bytes()
        tree = parser.parse(source)
        entries: list[SkeletonEntry] = []
        self._walk(tree.root_node, file, entries, source)
        return entries

    def _walk(
        self,
        node: Any,
        file: Path,
        entries: list[SkeletonEntry],
        source: bytes,
    ) -> None:
        if node.type == "function_declaration":
            name = self._get_child_text(node, "identifier", source)
            if name:
                entries.append(SkeletonEntry(
                    name=name,
                    kind="function",
                    file=str(file),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language="typescript" if file.suffix in (".ts", ".tsx") else "javascript",
                ))

        elif node.type in ("class_declaration", "abstract_class_declaration"):
            name = self._get_child_text(node, "type_identifier", source)
            if name:
                entries.append(SkeletonEntry(
                    name=name,
                    kind="class",
                    file=str(file),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language="typescript" if file.suffix in (".ts", ".tsx") else "javascript",
                ))
                self._extract_class_methods(node, name, file, entries, source)

        elif node.type == "interface_declaration":
            name = self._get_child_text(node, "type_identifier", source)
            if name:
                entries.append(SkeletonEntry(
                    name=name,
                    kind="interface",
                    file=str(file),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language="typescript",
                ))

        elif node.type == "type_alias_declaration":
            name = self._get_child_text(node, "type_identifier", source)
            if name:
                entries.append(SkeletonEntry(
                    name=name,
                    kind="type",
                    file=str(file),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language="typescript",
                ))

        elif node.type in ("lexical_declaration", "variable_declaration"):
            for child in node.children:
                if child.type == "variable_declarator":
                    vname = self._get_child_text(child, "identifier", source)
                    if vname and any(
                        c.type in ("arrow_function", "function")
                        for c in child.children
                    ):
                        entries.append(SkeletonEntry(
                            name=vname,
                            kind="function",
                            file=str(file),
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                            language="typescript" if file.suffix in (".ts", ".tsx") else "javascript",
                        ))

        for child in node.children:
            self._walk(child, file, entries, source)

    def _extract_class_methods(
        self, class_node: Any, class_name: str, file: Path,
        entries: list[SkeletonEntry], source: bytes,
    ) -> None:
        lang = "typescript" if file.suffix in (".ts", ".tsx") else "javascript"
        body = next((c for c in class_node.children if c.type == "class_body"), None)
        if body is None:
            return
        for member in body.children:
            if member.type in ("method_definition", "method_signature"):
                mname = self._get_child_text(member, "property_identifier", source)
                if not mname:
                    continue
                entries.append(SkeletonEntry(
                    name=f"{class_name}.{mname}",
                    kind="method",
                    file=str(file),
                    line_start=member.start_point[0] + 1,
                    line_end=member.end_point[0] + 1,
                    language=lang,
                ))
            elif member.type == "public_field_definition":
                fname = self._get_child_text(member, "property_identifier", source)
                if fname and any(
                    c.type in ("arrow_function", "function_expression")
                    for c in member.children
                ):
                    entries.append(SkeletonEntry(
                        name=f"{class_name}.{fname}",
                        kind="method",
                        file=str(file),
                        line_start=member.start_point[0] + 1,
                        line_end=member.end_point[0] + 1,
                        language=lang,
                    ))

    @staticmethod
    def _get_child_text(node: Any, child_type: str, source: bytes) -> str:
        for child in node.children:
            if child.type == child_type:
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return ""
