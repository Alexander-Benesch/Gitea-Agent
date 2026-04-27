from __future__ import annotations

import os
from pathlib import Path

import pytest

from samuel.cli import _activate_self_mode, _build_parser, _load_env_file
from samuel.core.config import FileConfig


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SAMUEL_SELF_MODE", "SAMUEL_ENV_FILE", "TEST_KEY", "OVERRIDE_KEY"):
        monkeypatch.delenv(var, raising=False)


class TestLoadEnvFile:
    def test_sets_variables(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text("TEST_KEY=value1\nOTHER=value2\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "value1"
        assert os.environ["OTHER"] == "value2"

    def test_setdefault_without_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY", "preexisting")
        env = tmp_path / ".env"
        env.write_text("TEST_KEY=new-value\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "preexisting"

    def test_override_replaces(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY", "preexisting")
        env = tmp_path / ".env"
        env.write_text("TEST_KEY=new-value\n")
        _load_env_file(env, override=True)
        assert os.environ["TEST_KEY"] == "new-value"

    def test_ignores_comments_and_empty_lines(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text("# comment\n\nTEST_KEY=x\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "x"

    def test_strips_quotes(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text('TEST_KEY="quoted-value"\n')
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "quoted-value"

    def test_missing_file_is_noop(self, tmp_path: Path, clean_env: None) -> None:
        _load_env_file(tmp_path / "missing.env", override=False)
        assert "TEST_KEY" not in os.environ


class TestActivateSelfMode:
    def test_loads_env_then_agent_override(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("TEST_KEY=base\nOVERRIDE_KEY=base\n")
        (tmp_path / ".env.agent").write_text("OVERRIDE_KEY=agent\n")

        agent_env = _activate_self_mode(tmp_path)

        assert os.environ["TEST_KEY"] == "base"
        assert os.environ["OVERRIDE_KEY"] == "agent"
        assert os.environ["SAMUEL_SELF_MODE"] == "1"
        assert agent_env == tmp_path / ".env.agent"

    def test_no_agent_env_still_sets_flag(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("TEST_KEY=base\n")
        agent_env = _activate_self_mode(tmp_path)
        assert os.environ["SAMUEL_SELF_MODE"] == "1"
        assert agent_env is None


class TestCliParser:
    def test_self_flag_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--self", "health"])
        assert args.self_mode is True
        assert args.command == "health"

    def test_default_is_not_self_mode(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["health"])
        assert args.self_mode is False


class TestConfigOverride:
    def test_override_takes_precedence(self, tmp_path: Path) -> None:
        (tmp_path / "agent.json").write_text('{"mode": "standard"}')
        cfg = FileConfig(tmp_path)
        assert cfg.get("agent.mode") == "standard"

        cfg._overrides["agent.mode"] = "self"
        assert cfg.get("agent.mode") == "self"

    def test_override_does_not_affect_other_keys(self, tmp_path: Path) -> None:
        (tmp_path / "agent.json").write_text('{"mode": "standard", "log_level": "INFO"}')
        cfg = FileConfig(tmp_path)
        cfg._overrides["agent.mode"] = "self"
        assert cfg.get("agent.log_level") == "INFO"


class TestSelfModeParity:
    """Self-Mode darf keine Security-Entscheidungen relaxen.

    Security-bezogene Slices dürfen SAMUEL_SELF_MODE / self_mode nicht
    referenzieren — das verhindert dass Gates oder Audit-Regeln
    im Self-Mode still abgeschaltet werden (Sandbox-Escape-Risk).
    """

    SECURITY_SLICES = [
        "samuel/slices/audit_trail",
        "samuel/slices/security",
        "samuel/slices/privacy",
        "samuel/slices/pr_gates",
    ]

    FORBIDDEN_PATTERNS = [
        "SAMUEL_SELF_MODE",
        "self_mode",
        '"--self"',
        "'--self'",
    ]

    def test_security_slices_do_not_reference_self_mode(self) -> None:
        repo_root = Path(__file__).parent.parent
        offenders: list[str] = []
        for slice_path in self.SECURITY_SLICES:
            for py_file in (repo_root / slice_path).rglob("*.py"):
                if "tests/" in str(py_file) or "test_" in py_file.name:
                    continue
                content = py_file.read_text(encoding="utf-8")
                for pattern in self.FORBIDDEN_PATTERNS:
                    if pattern in content:
                        offenders.append(f"{py_file.relative_to(repo_root)}: {pattern}")
        assert not offenders, (
            "Security-Slices dürfen Self-Mode nicht referenzieren:\n  "
            + "\n  ".join(offenders)
        )
