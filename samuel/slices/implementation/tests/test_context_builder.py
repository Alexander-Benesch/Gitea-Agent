from __future__ import annotations

import ast
from pathlib import Path

from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry
from samuel.slices.implementation.context_builder import (
    build_full_context,
    extract_keywords,
    extract_plan_files,
    filter_skeleton,
    grep_keywords,
    load_file_excerpt,
    render_files_section,
    render_grep_section,
    render_skeleton_section,
)


class PythonASTBuilder(ISkeletonBuilder):
    supported_extensions = {".py"}

    def extract(self, file: Path) -> list[SkeletonEntry]:
        tree = ast.parse(file.read_text())
        rel = str(file)
        entries: list[SkeletonEntry] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entries.append(SkeletonEntry(
                    name=node.name, kind="function", file=rel,
                    line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                ))
            elif isinstance(node, ast.ClassDef):
                entries.append(SkeletonEntry(
                    name=node.name, kind="class", file=rel,
                    line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                ))
        return entries


class TestExtractKeywords:
    def test_filters_stop_words(self) -> None:
        kws = extract_keywords("Issue: implement login handler", "please add tests for this")
        assert "login" in kws or "handler" in kws
        assert "issue" not in kws
        assert "please" not in kws
        assert "this" not in kws

    def test_orders_by_frequency(self) -> None:
        text = "foo foo foo bar bar baz"
        kws = extract_keywords(text)
        assert kws[0] == "foo"
        assert kws[1] == "bar"
        assert kws[2] == "baz"

    def test_ignores_short_tokens(self) -> None:
        kws = extract_keywords("ab cd ef xyzzy")
        assert kws == ["xyzzy"]

    def test_limit(self) -> None:
        words = " ".join(f"word{i:02d}xyz" for i in range(50))
        kws = extract_keywords(words, limit=5)
        assert len(kws) == 5


class TestExtractPlanFiles:
    def test_finds_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / "samuel").mkdir()
        (tmp_path / "samuel" / "cli.py").write_text("# cli")
        (tmp_path / "config.json").write_text("{}")

        plan = "Edit samuel/cli.py and config.json as described."
        files = extract_plan_files(plan, tmp_path)
        assert "samuel/cli.py" in files
        assert "config.json" in files

    def test_ignores_missing_files(self, tmp_path: Path) -> None:
        plan = "Edit missing.py please."
        files = extract_plan_files(plan, tmp_path)
        assert files == []

    def test_ignores_absolute_and_parent_paths(self, tmp_path: Path) -> None:
        (tmp_path / "foo.py").write_text("")
        plan = "/etc/passwd or ../../secret.txt or http://foo/bar"
        files = extract_plan_files(plan, tmp_path)
        assert files == []


class TestFilterSkeleton:
    def test_returns_empty_without_matches(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def unrelated_func():\n    pass\n")
        assert filter_skeleton([PythonASTBuilder()], tmp_path, issue_text="nothing here") == []

    def test_matches_symbol_in_issue_text(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def special_handler():\n    pass\n\ndef other():\n    pass\n")
        matches = filter_skeleton(
            [PythonASTBuilder()], tmp_path,
            issue_text="implement special_handler feature",
        )
        names = [entry.name for _rel, entry in matches]
        assert "special_handler" in names

    def test_backtick_symbols_boost_score(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def backticked():\n    pass\n\ndef plain_mention():\n    pass\n")
        matches = filter_skeleton(
            [PythonASTBuilder()], tmp_path,
            issue_text="Fix `backticked` and also plain_mention should work",
        )
        names = [entry.name for _rel, entry in matches]
        assert names[0] == "backticked"

    def test_plan_files_always_included(self, tmp_path: Path) -> None:
        src = tmp_path / "cli.py"
        src.write_text("def run():\n    pass\n")
        matches = filter_skeleton(
            [PythonASTBuilder()], tmp_path,
            issue_text="nothing",
            plan_files=["cli.py"],
        )
        assert any(rel == "cli.py" for rel, _ in matches)


class TestGrepKeywords:
    def test_finds_occurrences(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("def login():\n    x = 1\n")
        (tmp_path / "b.py").write_text("# unrelated\n")
        hits = grep_keywords(tmp_path, ["login"])
        assert "login" in hits
        assert hits["login"][0][0] == "a.py"
        assert hits["login"][0][1] == 1

    def test_respects_extension_filter(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("login")
        (tmp_path / "a.md").write_text("login")
        hits = grep_keywords(tmp_path, ["login"], extensions={".py"})
        assert len(hits["login"]) == 1

    def test_excludes_configured_dirs(self, tmp_path: Path) -> None:
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "x.py").write_text("login")
        hits = grep_keywords(tmp_path, ["login"])
        assert "login" not in hits


class TestLoadFileExcerpt:
    def test_loads_range(self, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("\n".join(f"line{i}" for i in range(10)))
        excerpt = load_file_excerpt(tmp_path, "f.py", start=3, end=5)
        assert "line2" in excerpt
        assert "line4" in excerpt
        assert "line5" not in excerpt

    def test_returns_empty_for_missing(self, tmp_path: Path) -> None:
        assert load_file_excerpt(tmp_path, "nope.py") == ""


class TestRendering:
    def test_skeleton_section_empty(self) -> None:
        assert render_skeleton_section([]) == ""

    def test_grep_section_includes_keyword(self) -> None:
        out = render_grep_section({"foo": [("a.py", 1, "def foo():")]})
        assert "foo" in out
        assert "a.py:1" in out

    def test_files_section(self, tmp_path: Path) -> None:
        (tmp_path / "x.py").write_text("print('hi')\n")
        out = render_files_section(tmp_path, ["x.py"])
        assert "x.py" in out
        assert "print" in out


class TestBuildFullContext:
    def test_end_to_end(self, tmp_path: Path) -> None:
        (tmp_path / "samuel").mkdir()
        (tmp_path / "samuel" / "cli.py").write_text(
            "def main():\n    pass\n\ndef setup_logging():\n    pass\n"
        )

        ctx = build_full_context(
            issue_number=42,
            issue_title="CLI setup logging support",
            issue_body="Add logging setup in samuel/cli.py",
            plan_text="Edit samuel/cli.py",
            project_root=tmp_path,
            skeleton_builders=[PythonASTBuilder()],
            architecture_constraints=["Kein Slice importiert Slice"],
        )
        assert "logging" in ctx["keywords"] or "setup" in ctx["keywords"]
        assert "samuel/cli.py" in ctx["plan_files"]
        assert "setup_logging" in ctx["skeleton"]
        assert "Architektur-Constraints" in ctx["constraints"]
