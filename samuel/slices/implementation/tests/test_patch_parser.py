from __future__ import annotations

from pathlib import Path

from samuel.slices.implementation.patch_parser import (
    JSONPatchApplier,
    LinePatchApplier,
    YAMLPatchApplier,
    get_applier,
    parse_patches,
)


class TestParsePatches:
    def test_search_replace(self):
        text = (
            "## handler.py\n"
            "<<<<<<< SEARCH\n"
            "old code\n"
            "=======\n"
            "new code\n"
            ">>>>>>> REPLACE\n"
        )
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["file"] == "handler.py"
        assert patches[0]["search"] == "old code"
        assert patches[0]["replace"] == "new code"

    def test_replace_lines(self):
        text = (
            "## handler.py\n"
            "REPLACE LINES 10-25\n"
            "new line 1\n"
            "new line 2\n"
            "END REPLACE\n"
        )
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["type"] == "replace_lines"
        assert patches[0]["lines"] == (10, 25)
        assert patches[0]["replace"] == "new line 1\nnew line 2"

    def test_write_block(self):
        text = (
            "## WRITE: docs/readme.md\n"
            "# Title\n"
            "Content here\n"
            "## END_WRITE\n"
        )
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["type"] == "write"
        assert patches[0]["file"] == "docs/readme.md"
        assert patches[0]["write"] == "# Title\nContent here"

    def test_multiple_patches(self):
        text = (
            "## a.py\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "## b.py\n"
            "<<<<<<< SEARCH\n"
            "x\n"
            "=======\n"
            "y\n"
            ">>>>>>> REPLACE\n"
        )
        patches = parse_patches(text)
        assert len(patches) == 2
        assert patches[0]["file"] == "a.py"
        assert patches[1]["file"] == "b.py"

    def test_empty_text(self):
        assert parse_patches("") == []

    def test_no_patches_in_text(self):
        assert parse_patches("just some text without patches") == []

    def test_incomplete_write_block(self):
        text = (
            "## WRITE: docs/readme.md\n"
            "content without end marker\n"
        )
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["type"] == "write"


class TestLinePatchApplier:
    def test_search_replace_apply(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\nold_var = 2\ny = 3\n")
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "test.py", "search": "old_var = 2", "replace": "new_var = 2"}])
        assert results[0][0] is True
        assert "new_var = 2" in f.read_text()

    def test_replace_lines_apply(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("a = 1\nb = 2\nc = 3\nd = 4\n")
        applier = LinePatchApplier()
        results = applier.apply(f, [{
            "file": "test.py", "type": "replace_lines",
            "lines": (2, 3), "replace": "replaced = 99",
        }])
        assert results[0][0] is True
        content = f.read_text()
        assert "replaced = 99" in content
        assert "b = 2" not in content

    def test_write_apply(self, tmp_path: Path):
        f = tmp_path / "new.md"
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "new.md", "type": "write", "write": "hello"}])
        assert results[0][0] is True
        assert f.read_text().strip() == "hello"

    def test_syntax_error_rejected(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("x = 1\n")
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "bad.py", "search": "x = 1", "replace": "def ("}])
        assert results[0][0] is False

    def test_search_not_found(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "test.py", "search": "nonexistent", "replace": "y = 2"}])
        assert results[0][0] is False

    def test_line_range_out_of_bounds(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\ny = 2\n")
        applier = LinePatchApplier()
        results = applier.apply(f, [{
            "file": "test.py", "type": "replace_lines",
            "lines": (1, 10), "replace": "x",
        }])
        assert results[0][0] is False

    def test_file_not_found(self, tmp_path: Path):
        f = tmp_path / "missing.py"
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "missing.py", "search": "x", "replace": "y"}])
        assert results[0][0] is False


class TestJSONPatchApplier:
    def test_valid_json_write(self, tmp_path: Path):
        f = tmp_path / "config.json"
        applier = JSONPatchApplier()
        results = applier.apply(f, [{"file": "config.json", "type": "write", "write": '{"key": "val"}'}])
        assert results[0][0] is True

    def test_invalid_json_rejected(self, tmp_path: Path):
        f = tmp_path / "config.json"
        applier = JSONPatchApplier()
        results = applier.apply(f, [{"file": "config.json", "type": "write", "write": "{invalid json"}])
        assert results[0][0] is False

    def test_validate_method(self, tmp_path: Path):
        applier = JSONPatchApplier()
        assert applier.validate(tmp_path / "x.json", '{"a": 1}') is True
        assert applier.validate(tmp_path / "x.json", "not json") is False


class TestRegistry:
    def test_python_gets_line_applier(self):
        assert isinstance(get_applier(Path("test.py")), LinePatchApplier)

    def test_json_gets_json_applier(self):
        assert isinstance(get_applier(Path("config.json")), JSONPatchApplier)

    def test_yaml_gets_yaml_applier(self):
        assert isinstance(get_applier(Path("config.yaml")), YAMLPatchApplier)
        assert isinstance(get_applier(Path("config.yml")), YAMLPatchApplier)

    def test_unknown_gets_fallback(self):
        assert isinstance(get_applier(Path("file.txt")), LinePatchApplier)
