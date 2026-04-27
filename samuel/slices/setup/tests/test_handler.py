from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from samuel.core.bus import Bus
from samuel.core.ports import IConfig
from samuel.slices.setup.handler import REQUIRED_DIRS, SetupHandler


class MockConfig(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return False


class FakeSCM:
    def __init__(self, existing: list[dict] | None = None, fail_on: set[str] | None = None) -> None:
        self._labels = list(existing or [])
        self._fail_on = fail_on or set()
        self.created: list[dict] = []

    def list_labels(self) -> list[dict]:
        return list(self._labels)

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        if name in self._fail_on:
            raise RuntimeError(f"simulated failure for {name}")
        new = {"id": len(self._labels) + 1, "name": name, "color": color, "description": description}
        self._labels.append(new)
        self.created.append(new)
        return new


class TestSetupHandler:
    def test_check_prerequisites_missing_dirs(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = SetupHandler(bus, project_root=tmp_path)

        result = handler.check_prerequisites()

        assert result["ready"] is False
        for d in REQUIRED_DIRS:
            assert any(d in issue for issue in result["issues"])

    def test_check_prerequisites_dirs_present(self, tmp_path: Path) -> None:
        bus = Bus()
        for d in REQUIRED_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        handler = SetupHandler(bus, project_root=tmp_path)

        result = handler.check_prerequisites()

        dir_issues = [i for i in result["issues"] if "directory missing" in i]
        assert len(dir_issues) == 0

    def test_ensure_directories_creates_dirs(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = SetupHandler(bus, project_root=tmp_path)

        created = handler.ensure_directories()

        assert len(created) == len(REQUIRED_DIRS)
        for d in REQUIRED_DIRS:
            assert (tmp_path / d).is_dir()
            assert d in created

    def test_ensure_directories_skips_existing(self, tmp_path: Path) -> None:
        bus = Bus()
        for d in REQUIRED_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        handler = SetupHandler(bus, project_root=tmp_path)

        created = handler.ensure_directories()

        assert len(created) == 0

    def test_ensure_then_check_prerequisites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        bus = Bus()
        monkeypatch.setenv("SCM_URL", "http://example.com")
        monkeypatch.setenv("SCM_TOKEN", "tok")
        monkeypatch.setenv("SCM_REPO", "owner/repo")
        handler = SetupHandler(bus, project_root=tmp_path)

        handler.ensure_directories()
        result = handler.check_prerequisites()

        assert result["ready"] is True
        assert result["issues"] == []

    def test_env_vars_missing_reported(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        bus = Bus()
        for d in REQUIRED_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        monkeypatch.delenv("SCM_URL", raising=False)
        monkeypatch.delenv("SCM_TOKEN", raising=False)
        monkeypatch.delenv("SCM_REPO", raising=False)
        monkeypatch.delenv("GITEA_URL", raising=False)
        monkeypatch.delenv("GITEA_TOKEN", raising=False)
        monkeypatch.delenv("GITEA_REPO", raising=False)
        handler = SetupHandler(bus, project_root=tmp_path)

        result = handler.check_prerequisites()

        assert result["ready"] is False
        env_issues = [i for i in result["issues"] if "env var missing" in i]
        assert len(env_issues) == 3


class TestServerHook:
    def test_install_server_hook(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = SetupHandler(bus, project_root=tmp_path)
        target_dir = tmp_path / "hooks"

        result = handler.install_server_hook(target_dir)

        assert result["installed"] is True
        hook_file = target_dir / "pre-receive"
        assert hook_file.exists()
        assert hook_file.stat().st_mode & 0o111
        content = hook_file.read_text()
        assert "PROTECTED_BRANCHES" in content
        assert "REJECTED" in content

    def test_install_creates_target_dir(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = SetupHandler(bus, project_root=tmp_path)
        target_dir = tmp_path / "deep" / "nested" / "hooks"

        result = handler.install_server_hook(target_dir)

        assert result["installed"] is True
        assert target_dir.exists()

    def test_get_hook_install_instructions(self) -> None:
        bus = Bus()
        handler = SetupHandler(bus)

        instructions = handler.get_hook_install_instructions("Alexmistrator/S.A.M.U.E.L")

        assert "pre-receive" in instructions
        assert "Alexmistrator/S.A.M.U.E.L" in instructions
        assert "--no-verify" in instructions


class TestSyncLabels:
    def _write_labels(self, tmp_path: Path, names: list[str]) -> Path:
        (tmp_path / "config").mkdir(exist_ok=True)
        labels_file = tmp_path / "config" / "labels.json"
        with open(labels_file, "w") as f:
            json.dump({"labels": [
                {"name": n, "color": "cccccc", "description": f"{n} desc"} for n in names
            ]}, f)
        return labels_file

    def test_sync_creates_missing_labels(self, tmp_path: Path) -> None:
        scm = FakeSCM(existing=[{"id": 1, "name": "ready-for-agent", "color": "0e8a16", "description": ""}])
        self._write_labels(tmp_path, ["ready-for-agent", "in-progress", "needs-review"])
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=scm)

        result = handler.sync_labels()

        assert result["synced"] is True
        assert result["created"] == ["in-progress", "needs-review"]
        assert result["skipped"] == ["ready-for-agent"]
        assert result["errors"] == []
        assert {l["name"] for l in scm.created} == {"in-progress", "needs-review"}

    def test_sync_is_idempotent(self, tmp_path: Path) -> None:
        scm = FakeSCM(existing=[
            {"id": 1, "name": "in-progress", "color": "1d76db", "description": ""},
            {"id": 2, "name": "needs-review", "color": "fbca04", "description": ""},
        ])
        self._write_labels(tmp_path, ["in-progress", "needs-review"])
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=scm)

        result = handler.sync_labels()

        assert result["synced"] is True
        assert result["created"] == []
        assert len(result["skipped"]) == 2
        assert scm.created == []

    def test_sync_reports_errors_but_continues(self, tmp_path: Path) -> None:
        scm = FakeSCM(existing=[], fail_on={"in-progress"})
        self._write_labels(tmp_path, ["ready-for-agent", "in-progress", "needs-review"])
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=scm)

        result = handler.sync_labels()

        assert result["synced"] is False
        assert "ready-for-agent" in result["created"]
        assert "needs-review" in result["created"]
        assert any("in-progress" in e for e in result["errors"])

    def test_sync_without_scm_returns_error(self, tmp_path: Path) -> None:
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=None)
        result = handler.sync_labels()
        assert result["synced"] is False
        assert "SCM not configured" in result["error"]

    def test_sync_with_missing_file_returns_error(self, tmp_path: Path) -> None:
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=FakeSCM())
        result = handler.sync_labels(tmp_path / "does-not-exist.json")
        assert result["synced"] is False
        assert "not found" in result["error"]
