from __future__ import annotations

from pathlib import Path

from samuel.core.bus import Bus
from samuel.slices.code_analysis.handler import CodeAnalysisHandler


class TestCodeAnalysisHandler:
    def test_syntax_check_pass(self, tmp_path: Path) -> None:
        bus = Bus()
        good_file = tmp_path / "good.py"
        good_file.write_text("x = 1\n")
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(good_file)])

        assert result["passed"] is True
        assert result["checks"]["syntax"]["passed"] is True
        assert result["checks"]["syntax"]["errors"] == []

    def test_syntax_check_fail(self, tmp_path: Path) -> None:
        bus = Bus()
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(\n")
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(bad_file)])

        assert result["passed"] is False
        assert result["checks"]["syntax"]["passed"] is False
        assert len(result["checks"]["syntax"]["errors"]) == 1

    def test_syntax_check_multiple_files(self, tmp_path: Path) -> None:
        bus = Bus()
        good = tmp_path / "ok.py"
        good.write_text("a = 1\n")
        bad = tmp_path / "nope.py"
        bad.write_text("if:\n")
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(good), str(bad)])

        assert result["checks"]["syntax"]["passed"] is False
        assert len(result["checks"]["syntax"]["errors"]) == 1

    def test_cross_slice_import_detected(self, tmp_path: Path) -> None:
        bus = Bus()
        # Create slice structure: slices/alpha/mod.py imports slices/beta
        slice_dir = tmp_path / "slices" / "alpha"
        slice_dir.mkdir(parents=True)
        offending = slice_dir / "mod.py"
        offending.write_text("from samuel.slices.beta.handler import BetaHandler\n")
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(offending)])

        assert result["checks"]["imports"]["passed"] is False
        assert len(result["checks"]["imports"]["violations"]) == 1
        assert "beta" in result["checks"]["imports"]["violations"][0]

    def test_no_cross_slice_when_only_core_imports(self, tmp_path: Path) -> None:
        bus = Bus()
        slice_dir = tmp_path / "slices" / "alpha"
        slice_dir.mkdir(parents=True)
        ok_file = slice_dir / "utils.py"
        ok_file.write_text("from samuel.core.bus import Bus\nimport os\n")
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(ok_file)])

        assert result["checks"]["imports"]["passed"] is True
        assert result["checks"]["imports"]["violations"] == []

    def test_non_slice_file_skips_import_check(self, tmp_path: Path) -> None:
        bus = Bus()
        core_file = tmp_path / "core" / "bus.py"
        core_file.parent.mkdir(parents=True)
        core_file.write_text("from samuel.slices.health.handler import HealthHandler\n")
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(core_file)])

        # core files are not in "slices/" path, so import check skips them
        assert result["checks"]["imports"]["passed"] is True

    def test_missing_file_ignored(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = CodeAnalysisHandler(bus, project_root=tmp_path)

        result = handler.run_checks(files=[str(tmp_path / "nonexistent.py")])

        assert result["checks"]["syntax"]["passed"] is True
