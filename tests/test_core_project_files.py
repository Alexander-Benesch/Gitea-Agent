from __future__ import annotations

from pathlib import Path

import pytest

from samuel.core.project_files import (
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DEFAULT_EXCLUDE_DIRS,
    DEFAULT_EXCLUDE_FILES,
    DOC_EXTENSIONS,
    iter_project_files,
    list_project_files,
)


class TestIterProjectFiles:
    def test_returns_all_files_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.txt").write_text("")
        files = list(iter_project_files(tmp_path))
        names = {f.name for f in files}
        assert names == {"a.py", "b.txt"}

    def test_filters_by_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.js").write_text("")
        (tmp_path / "c.md").write_text("")
        files = list(iter_project_files(tmp_path, extensions={".py", ".js"}))
        names = {f.name for f in files}
        assert names == {"a.py", "b.js"}

    def test_excludes_default_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("")

        files = list(iter_project_files(tmp_path))
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert rels == {"src/a.py"}

    def test_excludes_default_lock_files(self, tmp_path: Path) -> None:
        (tmp_path / "package-lock.json").write_text("{}")
        (tmp_path / "Cargo.lock").write_text("")
        (tmp_path / "real.json").write_text("{}")
        files = list(iter_project_files(tmp_path))
        names = {f.name for f in files}
        assert "package-lock.json" not in names
        assert "Cargo.lock" not in names
        assert "real.json" in names

    def test_user_exclude_dirs_merged(self, tmp_path: Path) -> None:
        (tmp_path / "fixtures").mkdir()
        (tmp_path / "fixtures" / "a.py").write_text("")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "b.py").write_text("")

        files = list(iter_project_files(tmp_path, exclude_dirs={"fixtures"}))
        names = {f.name for f in files}
        assert names == {"b.py"}

    def test_max_size_filter(self, tmp_path: Path) -> None:
        (tmp_path / "small.py").write_text("x" * 100)
        (tmp_path / "big.py").write_text("x" * 10000)
        files = list(iter_project_files(tmp_path, max_size_kb=5))
        names = {f.name for f in files}
        assert names == {"small.py"}

    def test_nested_directories(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "x.py").write_text("")
        files = list(iter_project_files(tmp_path))
        assert len(files) == 1
        assert files[0].name == "x.py"

    def test_returns_nothing_for_missing_root(self, tmp_path: Path) -> None:
        files = list(iter_project_files(tmp_path / "nope"))
        assert files == []

    def test_symlinks_skipped_by_default(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("")
        link = tmp_path / "link"
        try:
            link.symlink_to(src_dir)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported here")
        files = list(iter_project_files(tmp_path))
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "src_dir/a.py" in rels
        assert "link/a.py" not in rels

    def test_list_project_files_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "c.py").write_text("")
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        files = list_project_files(tmp_path)
        names = [f.name for f in files]
        assert names == sorted(names)


class TestExtensionConstants:
    def test_code_extensions_include_major_langs(self) -> None:
        for ext in (".py", ".js", ".ts", ".go", ".java", ".rs", ".rb", ".php", ".cpp"):
            assert ext in CODE_EXTENSIONS

    def test_config_extensions(self) -> None:
        for ext in (".json", ".yaml", ".yml", ".toml"):
            assert ext in CONFIG_EXTENSIONS

    def test_doc_extensions(self) -> None:
        for ext in (".md", ".rst", ".txt"):
            assert ext in DOC_EXTENSIONS

    def test_extensions_dont_overlap(self) -> None:
        assert not (CODE_EXTENSIONS & CONFIG_EXTENSIONS)
        assert not (CODE_EXTENSIONS & DOC_EXTENSIONS)

    def test_defaults_frozen(self) -> None:
        assert isinstance(DEFAULT_EXCLUDE_DIRS, frozenset)
        assert isinstance(DEFAULT_EXCLUDE_FILES, frozenset)
