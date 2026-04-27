from __future__ import annotations

from pathlib import Path

from samuel.core.bus import Bus
from samuel.slices.architecture.handler import ArchitectureHandler


def _make_slice_structure(root: Path, slices: dict[str, dict[str, str]], *, with_tests: bool = True) -> None:
    """Create a minimal samuel/slices/<name>/ structure under root."""
    slices_dir = root / "samuel" / "slices"
    for slice_name, files in slices.items():
        slice_dir = slices_dir / slice_name
        slice_dir.mkdir(parents=True, exist_ok=True)
        if with_tests:
            tests_dir = slice_dir / "tests"
            tests_dir.mkdir(exist_ok=True)
            (tests_dir / "__init__.py").write_text("")
        for filename, content in files.items():
            (slice_dir / filename).write_text(content)


class TestValidateArchitecture:
    def test_clean_architecture_is_valid(self, tmp_path: Path):
        _make_slice_structure(tmp_path, {
            "planning": {"handler.py": "from samuel.core.bus import Bus\n"},
            "context": {"handler.py": "import logging\n"},
        })
        bus = Bus()
        handler = ArchitectureHandler(bus, project_root=tmp_path)

        result = handler.validate_architecture()

        assert result["valid"] is True
        assert result["violations"] == []

    def test_cross_slice_import_detected(self, tmp_path: Path):
        _make_slice_structure(tmp_path, {
            "planning": {"handler.py": "from samuel.slices.context.handler import ContextHandler\n"},
            "context": {"handler.py": "import logging\n"},
        })
        bus = Bus()
        handler = ArchitectureHandler(bus, project_root=tmp_path)

        result = handler.validate_architecture()

        assert result["valid"] is False
        assert len(result["violations"]) >= 1
        assert "cross-slice import" in result["violations"][0]
        assert "context" in result["violations"][0]

    def test_same_slice_import_not_flagged(self, tmp_path: Path):
        _make_slice_structure(tmp_path, {
            "planning": {
                "handler.py": "from samuel.slices.planning.utils import helper\n",
                "utils.py": "def helper(): pass\n",
            },
        })
        bus = Bus()
        handler = ArchitectureHandler(bus, project_root=tmp_path)

        result = handler.validate_architecture()

        assert result["valid"] is True

    def test_missing_tests_directory_detected(self, tmp_path: Path):
        _make_slice_structure(tmp_path, {
            "planning": {"handler.py": "pass\n"},
        }, with_tests=False)
        bus = Bus()
        handler = ArchitectureHandler(bus, project_root=tmp_path)

        result = handler.validate_architecture()

        assert result["valid"] is False
        assert any("missing tests/" in v for v in result["violations"])

    def test_empty_slices_dir_is_valid(self, tmp_path: Path):
        slices_dir = tmp_path / "samuel" / "slices"
        slices_dir.mkdir(parents=True)
        bus = Bus()
        handler = ArchitectureHandler(bus, project_root=tmp_path)

        result = handler.validate_architecture()

        assert result["valid"] is True


class TestGetConstraints:
    def test_returns_constraints_list(self):
        bus = Bus()
        handler = ArchitectureHandler(bus)
        constraints = handler.get_constraints()

        assert len(constraints) >= 4
        assert any("Slice" in c for c in constraints)
