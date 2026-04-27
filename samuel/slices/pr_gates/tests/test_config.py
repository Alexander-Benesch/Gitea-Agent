from __future__ import annotations

from pathlib import Path

import pytest

from samuel.core.config import GatesConfigSchema, load_gates_config


class TestGatesConfigSchema:
    def test_default_values(self):
        cfg = GatesConfigSchema()
        assert 1 in cfg.required
        assert 4 in cfg.optional
        assert cfg.disabled == []
        assert cfg.custom == []

    def test_custom_values(self):
        cfg = GatesConfigSchema(
            required=[1, 2],
            optional=[3],
            disabled=[6],
            custom=[{"name": "test", "type": "webhook"}],
        )
        assert cfg.required == [1, 2]
        assert cfg.disabled == [6]

    def test_string_gate_ids(self):
        cfg = GatesConfigSchema(required=["13a", "13b"], optional=[])
        assert "13a" in cfg.required


class TestLoadGatesConfig:
    def test_loads_from_file(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [1, 2], "optional": [3], "disabled": [6], "custom": []}'
        )
        cfg = load_gates_config(tmp_path)
        assert cfg.required == [1, 2]
        assert cfg.disabled == [6]

    def test_missing_file_returns_default(self, tmp_path: Path):
        cfg = load_gates_config(tmp_path)
        assert 1 in cfg.required
        assert cfg.disabled == []

    def test_invalid_json_raises(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text("{invalid json")
        with pytest.raises(ValueError, match="Invalid gates.json"):
            load_gates_config(tmp_path)

    def test_disabled_gate_6_skipped(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [1, 2, 3], "optional": [4, 5], "disabled": [6], "custom": []}'
        )
        cfg = load_gates_config(tmp_path)
        assert 6 in cfg.disabled
        assert 6 not in cfg.required
        assert 6 not in cfg.optional
