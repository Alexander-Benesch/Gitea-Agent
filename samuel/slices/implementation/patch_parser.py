from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from samuel.core.ports import IPatchApplier


def _normalize_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


def parse_patches(text: str) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    current_file: str | None = None
    state = "idle"
    search_lines: list[str] = []
    replace_lines: list[str] = []
    write_lines: list[str] = []
    replace_line_range: tuple[int, int] | None = None

    for line in text.splitlines():
        stripped = line.rstrip()

        if state == "idle" and current_file:
            rl_match = re.match(r"REPLACE\s+LINES?\s+(\d+)\s*[-–]\s*(\d+)", stripped)
            if rl_match:
                replace_line_range = (int(rl_match.group(1)), int(rl_match.group(2)))
                state = "replace_lines"
                replace_lines = []
                continue

        if state == "replace_lines":
            if stripped in ("END REPLACE", "END_REPLACE"):
                patches.append({
                    "file": current_file,
                    "lines": replace_line_range,
                    "replace": "\n".join(replace_lines),
                    "type": "replace_lines",
                })
                state = "idle"
                replace_lines = []
                replace_line_range = None
            else:
                replace_lines.append(line)
            continue

        if state == "idle" and stripped.startswith("## WRITE: "):
            current_file = stripped[len("## WRITE: "):].strip()
            state = "write"
            write_lines = []
            continue

        if state == "write":
            if stripped == "## END_WRITE":
                patches.append({
                    "file": current_file,
                    "write": "\n".join(write_lines),
                    "type": "write",
                })
                state = "idle"
                write_lines = []
            else:
                write_lines.append(line)
            continue

        if state == "idle" and stripped.startswith("## ") and "." in stripped[3:]:
            current_file = stripped[3:].strip()
        elif stripped == "<<<<<<< SEARCH" and current_file:
            state = "search"
            search_lines = []
        elif stripped == "=======" and state == "search":
            state = "replace"
            replace_lines = []
        elif stripped == ">>>>>>> REPLACE" and state == "replace":
            patches.append({
                "file": current_file,
                "search": "\n".join(search_lines),
                "replace": "\n".join(replace_lines),
            })
            state = "idle"
            search_lines = []
            replace_lines = []
        elif state == "search":
            search_lines.append(line)
        elif state == "replace":
            replace_lines.append(line)

    if state == "write" and write_lines:
        patches.append({
            "file": current_file,
            "write": "\n".join(write_lines),
            "type": "write",
        })

    return patches


class LinePatchApplier(IPatchApplier):
    supported_extensions = {"*"}

    def apply(self, file: Path, patches: list[Any]) -> Any:
        results: list[tuple[bool, str]] = []
        for patch in patches:
            ok, msg = self._apply_one(file, patch)
            results.append((ok, msg))
        return results

    def _apply_one(self, file: Path, patch: dict) -> tuple[bool, str]:
        rel = patch.get("file", "")

        if patch.get("type") == "write":
            content = _normalize_ws(patch["write"])
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content + "\n", encoding="utf-8")
            return True, f"{rel} written"

        if not file.exists():
            return False, f"{rel} not found"

        original = file.read_text(encoding="utf-8")

        if patch.get("type") == "replace_lines":
            orig_lines = original.splitlines(keepends=True)
            start, end = patch["lines"]
            if start < 1 or end > len(orig_lines):
                return False, f"line range {start}-{end} out of bounds ({len(orig_lines)} lines)"
            new_replace = _normalize_ws(patch["replace"])
            new_lines = orig_lines[:start - 1] + [new_replace + "\n"] + orig_lines[end:]
            new_content = "".join(new_lines)
        else:
            norm_orig = _normalize_ws(original)
            norm_search = _normalize_ws(patch.get("search", ""))
            if norm_search not in norm_orig:
                return False, f"SEARCH not found in {rel}"
            new_content = norm_orig.replace(norm_search, _normalize_ws(patch.get("replace", "")), 1)

        if not self.validate(file, new_content):
            return False, f"validation failed for {rel}"

        file.write_text(new_content, encoding="utf-8")
        return True, f"{rel} patched"

    def validate(self, file: Path, content: str) -> bool:
        if file.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError:
                return False
        return True


class JSONPatchApplier(IPatchApplier):
    supported_extensions = {".json"}

    def apply(self, file: Path, patches: list[Any]) -> Any:
        results: list[tuple[bool, str]] = []
        for patch in patches:
            if patch.get("type") == "write":
                content = patch["write"]
                if not self.validate(file, content):
                    results.append((False, f"{patch.get('file', '')} invalid JSON after patch"))
                    continue
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding="utf-8")
                results.append((True, f"{patch.get('file', '')} written"))
            else:
                line_applier = LinePatchApplier()
                result = line_applier._apply_one(file, patch)
                if result[0]:
                    new_content = file.read_text(encoding="utf-8")
                    if not self.validate(file, new_content):
                        results.append((False, f"{patch.get('file', '')} invalid JSON after patch"))
                        continue
                results.append(result)
        return results

    def validate(self, file: Path, content: str) -> bool:
        try:
            json.loads(content)
            return True
        except (json.JSONDecodeError, ValueError):
            return False


class YAMLPatchApplier(IPatchApplier):
    supported_extensions = {".yaml", ".yml"}

    def apply(self, file: Path, patches: list[Any]) -> Any:
        line_applier = LinePatchApplier()
        return line_applier.apply(file, patches)

    def validate(self, file: Path, content: str) -> bool:
        return True


PATCH_APPLIERS: dict[str, IPatchApplier] = {
    ".py": LinePatchApplier(),
    ".json": JSONPatchApplier(),
    ".yaml": YAMLPatchApplier(),
    ".yml": YAMLPatchApplier(),
    "*": LinePatchApplier(),
}


def get_applier(file_path: Path) -> IPatchApplier:
    return PATCH_APPLIERS.get(file_path.suffix, PATCH_APPLIERS["*"])
