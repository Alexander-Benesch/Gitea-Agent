from __future__ import annotations

from pathlib import Path

import pytest

from samuel.adapters.quality.checks import (
    DiffSizeCheck,
    PythonSyntaxCheck,
    ScopeGuard,
    TreeSitterTypeScriptCheck,
)
from samuel.adapters.quality.registry import (
    QUALITY_CHECKS,
    get_checks_for,
    load_registry_from_config,
    register_check,
)


class TestPythonSyntaxCheck:
    def test_valid_python(self, tmp_path: Path):
        f = tmp_path / "good.py"
        f.write_text("def hello():\n    return 42\n")

        check = PythonSyntaxCheck()
        result = check.run(f, f.read_text(), {})

        assert result["passed"] is True

    def test_invalid_python(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("def hello(\n")

        check = PythonSyntaxCheck()
        result = check.run(f, f.read_text(), {})

        assert result["passed"] is False
        assert "SyntaxError" in result["reason"]

    def test_supported_extensions(self):
        assert PythonSyntaxCheck().supported_extensions == {".py"}


class TestTreeSitterTypeScriptCheck:
    def test_valid_typescript(self, tmp_path: Path):
        f = tmp_path / "good.ts"
        f.write_text("function hello(): number { return 42; }\n")

        check = TreeSitterTypeScriptCheck()
        result = check.run(f, f.read_text(), {})

        assert result["passed"] is True

    def test_invalid_typescript(self, tmp_path: Path):
        f = tmp_path / "bad.ts"
        f.write_text("function hello( { return; }\n")

        check = TreeSitterTypeScriptCheck()
        result = check.run(f, f.read_text(), {})

        if result.get("skipped"):
            pytest.skip("tree-sitter not available")
        assert result["passed"] is False

    def test_supported_extensions(self):
        check = TreeSitterTypeScriptCheck()
        assert ".ts" in check.supported_extensions
        assert ".tsx" in check.supported_extensions
        assert ".js" in check.supported_extensions


class TestScopeGuard:
    def test_clean_code(self, tmp_path: Path):
        f = tmp_path / "clean.py"
        content = "import os\nresult = os.path.join('a', 'b')\n"
        f.write_text(content)

        result = ScopeGuard().run(f, content, {})

        assert result["passed"] is True

    def test_dangerous_os_system(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        content = "import os\nos.system('rm -rf /')\n"
        f.write_text(content)

        result = ScopeGuard().run(f, content, {})

        assert result["passed"] is False
        assert len(result["violations"]) >= 1

    def test_dangerous_eval(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        content = "x = eval(input())\n"
        f.write_text(content)

        result = ScopeGuard().run(f, content, {})

        assert result["passed"] is False

    def test_wildcard_extension(self):
        assert ScopeGuard().supported_extensions == {"*"}


class TestDiffSizeCheck:
    def test_small_file(self, tmp_path: Path):
        f = tmp_path / "small.py"
        content = "x = 1\n" * 100
        f.write_text(content)

        result = DiffSizeCheck().run(f, content, {})

        assert result["passed"] is True

    def test_large_file(self, tmp_path: Path):
        f = tmp_path / "huge.py"
        content = "x = 1\n" * 6000
        f.write_text(content)

        result = DiffSizeCheck().run(f, content, {})

        assert result["passed"] is False


class TestRegistry:
    def test_load_defaults(self):
        load_registry_from_config()

        py_checks = get_checks_for(".py")
        assert len(py_checks) >= 2

        ts_checks = get_checks_for(".ts")
        assert len(ts_checks) >= 2

    def test_wildcard_included(self):
        load_registry_from_config()

        unknown = get_checks_for(".unknown")
        assert len(unknown) >= 1

    def test_register_custom_check(self):
        QUALITY_CHECKS.clear()

        class CustomCheck:
            supported_extensions = {".custom"}
            def run(self, file, content, skeleton):
                return {"passed": True}

        register_check(CustomCheck())
        checks = get_checks_for(".custom")
        assert len(checks) == 1

    def test_config_override_disabled(self, tmp_path: Path):
        config = tmp_path / "hooks.json"
        config.write_text('{"quality_checks": {"disabled": [".ts", ".tsx"]}}')

        load_registry_from_config(config)

        ts_checks = get_checks_for(".ts")
        wildcard_only = all(
            "*" in c.supported_extensions
            for c in ts_checks
        )
        assert wildcard_only or len(ts_checks) == len(get_checks_for(".unknown"))
