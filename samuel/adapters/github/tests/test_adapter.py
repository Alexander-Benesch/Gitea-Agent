from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from samuel.adapters.github.adapter import GitHubAdapter
from samuel.adapters.github.auth import GitHubAppAuth, GitHubTokenAuth
from samuel.core.ports import IAuthProvider
from samuel.core.types import PR, Issue


def _generate_rsa_pem() -> str:
    """Generate a test RSA private key in PEM format."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    except ImportError:
        return ""


class MockAuth(IAuthProvider):
    def get_token(self) -> str:
        return "ghp_test_token"

    def is_valid(self) -> bool:
        return True

    def refresh(self) -> None:
        pass


def _make_adapter(responses: list[dict | list]) -> tuple[GitHubAdapter, MagicMock]:
    auth = MockAuth()
    adapter = GitHubAdapter("owner/repo", auth, base_url="https://api.github.com")

    call_count = 0

    def mock_request(method: str, path: str, data: dict | None = None) -> Any:
        nonlocal call_count
        if call_count < len(responses):
            resp = responses[call_count]
            call_count += 1
            return resp
        return None

    adapter._api.request = MagicMock(side_effect=mock_request)
    return adapter, adapter._api.request


class TestGitHubAdapter:
    def test_capabilities(self):
        adapter = GitHubAdapter("o/r", MockAuth())
        caps = adapter.capabilities
        assert "labels" in caps
        assert "webhooks_full" in caps
        assert "checks" in caps

    def test_get_issue(self):
        adapter, mock = _make_adapter([{
            "number": 42,
            "title": "Test issue",
            "body": "Body text",
            "state": "open",
            "labels": [{"id": 1, "name": "bug"}],
        }])

        issue = adapter.get_issue(42)

        assert isinstance(issue, Issue)
        assert issue.number == 42
        assert issue.title == "Test issue"
        assert len(issue.labels) == 1
        assert issue.labels[0].name == "bug"
        mock.assert_called_once_with("GET", "/repos/owner/repo/issues/42")

    def test_get_comments(self):
        adapter, mock = _make_adapter([[
            {"id": 1, "body": "First", "user": {"login": "alice"}, "created_at": "2026-01-01"},
            {"id": 2, "body": "Second", "user": {"login": "bob"}, "created_at": "2026-01-02"},
        ]])

        comments = adapter.get_comments(10)

        assert len(comments) == 2
        assert comments[0].user == "alice"
        assert comments[1].body == "Second"

    def test_post_comment(self):
        adapter, mock = _make_adapter([
            {"id": 99, "body": "My comment", "user": {"login": "bot"}, "created_at": "2026-01-01"},
        ])

        comment = adapter.post_comment(10, "My comment")

        assert comment.id == 99
        mock.assert_called_once_with(
            "POST", "/repos/owner/repo/issues/10/comments", {"body": "My comment"},
        )

    def test_create_pr(self):
        adapter, mock = _make_adapter([{
            "id": 5, "number": 100, "title": "New PR",
            "html_url": "https://github.com/owner/repo/pull/100",
            "state": "open", "merged": False,
        }])

        pr = adapter.create_pr("feature", "main", "New PR", "Description")

        assert isinstance(pr, PR)
        assert pr.number == 100
        assert pr.html_url == "https://github.com/owner/repo/pull/100"

    def test_list_issues_filters_prs(self):
        adapter, mock = _make_adapter([[
            {"number": 1, "title": "Issue", "state": "open", "labels": []},
            {"number": 2, "title": "PR as issue", "state": "open", "labels": [],
             "pull_request": {"url": "..."}},
        ]])

        issues = adapter.list_issues([])

        assert len(issues) == 1
        assert issues[0].number == 1

    def test_close_issue(self):
        adapter, mock = _make_adapter([None])
        adapter.close_issue(42)
        mock.assert_called_once_with("PATCH", "/repos/owner/repo/issues/42", {"state": "closed"})

    def test_merge_pr(self):
        adapter, mock = _make_adapter([None])
        result = adapter.merge_pr(100)
        assert result is True
        mock.assert_called_once_with("PUT", "/repos/owner/repo/pulls/100/merge", {"merge_method": "merge"})

    def test_issue_url_github_com(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert adapter.issue_url(42) == "https://github.com/owner/repo/issues/42"

    def test_pr_url_github_com(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert adapter.pr_url(10) == "https://github.com/owner/repo/pull/10"

    def test_branch_url(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert adapter.branch_url("feat/x") == "https://github.com/owner/repo/tree/feat/x"

    def test_swap_label(self):
        adapter, mock = _make_adapter([None, None])
        adapter.swap_label(5, "old-label", "new-label")
        assert mock.call_count == 2

    def test_list_labels(self):
        adapter, mock = _make_adapter([[
            {"id": 1, "name": "bug", "color": "ff0000", "description": "a bug"},
            {"id": 2, "name": "docs", "color": "00ff00", "description": None},
        ]])
        labels = adapter.list_labels()
        assert len(labels) == 2
        assert labels[0]["name"] == "bug"
        assert labels[1]["description"] == ""
        mock.assert_called_once_with("GET", "/repos/owner/repo/labels?per_page=100")

    def test_create_label(self):
        adapter, mock = _make_adapter([{
            "id": 99, "name": "new-label", "color": "abcdef", "description": "x",
        }])
        result = adapter.create_label("new-label", "abcdef", "x")
        assert result["name"] == "new-label"
        mock.assert_called_once_with(
            "POST", "/repos/owner/repo/labels",
            {"name": "new-label", "color": "abcdef", "description": "x"},
        )


class TestGitHubTokenAuth:
    def test_token_auth(self):
        auth = GitHubTokenAuth("ghp_abc123")
        assert auth.get_token() == "ghp_abc123"
        assert auth.is_valid() is True
        auth.refresh()

    def test_empty_token_invalid(self):
        auth = GitHubTokenAuth("")
        assert auth.is_valid() is False


class TestGitHubAppAuth:
    def test_creates_jwt(self):
        pem = _generate_rsa_pem()
        if not pem:
            pytest.skip("cryptography package not installed")
        auth = GitHubAppAuth("12345", pem, "67890")
        jwt = auth._create_jwt()
        parts = jwt.split(".")
        assert len(parts) == 3

    def test_token_refresh_needed_initially(self):
        auth = GitHubAppAuth("12345", "secret-key", "67890")
        assert auth.is_valid() is False
