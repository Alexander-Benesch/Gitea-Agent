from __future__ import annotations

import pytest

from samuel.core.config import SCMConfig, load_scm_config


class TestSCMConfigNew:
    def test_loads_from_scm_vars(self, monkeypatch):
        monkeypatch.setenv("SCM_PROVIDER", "gitea")
        monkeypatch.setenv("SCM_URL", "http://gitea.local")
        monkeypatch.setenv("SCM_TOKEN", "tok-123")
        monkeypatch.setenv("SCM_REPO", "owner/repo")
        monkeypatch.setenv("SCM_USER", "admin")
        monkeypatch.setenv("SCM_BOT_USER", "bot")

        cfg = load_scm_config()
        assert cfg.provider == "gitea"
        assert cfg.url == "http://gitea.local"
        assert cfg.token == "tok-123"
        assert cfg.repo == "owner/repo"
        assert cfg.user == "admin"
        assert cfg.bot_user == "bot"

    def test_defaults_provider_to_gitea(self, monkeypatch):
        monkeypatch.setenv("SCM_URL", "http://gitea.local")
        monkeypatch.setenv("SCM_TOKEN", "tok")
        monkeypatch.setenv("SCM_REPO", "o/r")
        monkeypatch.delenv("SCM_PROVIDER", raising=False)

        cfg = load_scm_config()
        assert cfg.provider == "gitea"


class TestSCMConfigLegacy:
    def test_maps_gitea_vars(self, monkeypatch):
        monkeypatch.delenv("SCM_PROVIDER", raising=False)
        monkeypatch.delenv("SCM_URL", raising=False)
        monkeypatch.setenv("GITEA_URL", "http://legacy.local")
        monkeypatch.setenv("GITEA_TOKEN", "old-tok")
        monkeypatch.setenv("GITEA_REPO", "old/repo")
        monkeypatch.setenv("GITEA_USER", "olduser")
        monkeypatch.setenv("GITEA_BOT_USER", "oldbot")

        cfg = load_scm_config()
        assert cfg.provider == "gitea"
        assert cfg.url == "http://legacy.local"
        assert cfg.token == "old-tok"
        assert cfg.repo == "old/repo"

    def test_scm_takes_precedence_over_legacy(self, monkeypatch):
        monkeypatch.setenv("SCM_URL", "http://new.local")
        monkeypatch.setenv("SCM_TOKEN", "new-tok")
        monkeypatch.setenv("SCM_REPO", "new/repo")
        monkeypatch.setenv("GITEA_URL", "http://old.local")

        cfg = load_scm_config()
        assert cfg.url == "http://new.local"


class TestSCMConfigMissing:
    def test_raises_without_config(self, monkeypatch):
        for var in ("SCM_PROVIDER", "SCM_URL", "SCM_TOKEN", "SCM_REPO",
                     "GITEA_URL", "GITEA_TOKEN", "GITEA_REPO"):
            monkeypatch.delenv(var, raising=False)

        with pytest.raises(ValueError, match="SCM not configured"):
            load_scm_config()


class TestSCMConfigSchema:
    def test_pydantic_validation(self):
        cfg = SCMConfig(url="http://x", token="t", repo="o/r")
        assert cfg.provider == "gitea"
        assert cfg.user == ""
