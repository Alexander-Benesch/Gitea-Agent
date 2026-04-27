"""Integration tests for GiteaAdapter against a real Gitea instance.

Skipped unless SCM_URL and SCM_TOKEN env vars are set.
Tries to load .env file if env vars are not already present.
Uses an existing issue (reads only, no writes) to avoid side effects.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.adapter import GiteaAdapter
from samuel.core.types import Comment, Issue


def _load_env_fallback() -> None:
    for env_path in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and not os.environ.get(key):
                    os.environ[key] = value
            break


_load_env_fallback()

GITEA_URL = os.environ.get("SCM_URL", "") or os.environ.get("GITEA_URL", "")
GITEA_TOKEN = os.environ.get("SCM_TOKEN", "") or os.environ.get("GITEA_TOKEN", "")
GITEA_REPO = os.environ.get("SCM_REPO", "") or os.environ.get("GITEA_REPO", "")

skip_no_gitea = pytest.mark.skipif(
    not (GITEA_URL and GITEA_TOKEN and GITEA_REPO),
    reason="SCM_URL / SCM_TOKEN / SCM_REPO not set",
)


@pytest.fixture
def adapter():
    auth = StaticTokenAuth(GITEA_TOKEN)
    return GiteaAdapter(GITEA_URL, GITEA_REPO, auth)


@skip_no_gitea
class TestGiteaIntegration:
    def test_get_issue(self, adapter):
        issue = adapter.get_issue(12)
        assert isinstance(issue, Issue)
        assert issue.number == 12
        assert "Phase 2" in issue.title

    def test_get_comments(self, adapter):
        comments = adapter.get_comments(12)
        assert isinstance(comments, list)
        for c in comments:
            assert isinstance(c, Comment)

    def test_list_issues(self, adapter):
        issues = adapter.list_issues(["phase:2"])
        assert isinstance(issues, list)
        assert all(isinstance(i, Issue) for i in issues)

    def test_issue_url(self, adapter):
        url = adapter.issue_url(12)
        assert "/issues/12" in url
        assert GITEA_URL in url

    def test_capabilities(self, adapter):
        assert "labels" in adapter.capabilities
