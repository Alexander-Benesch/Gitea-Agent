from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.adapter import GiteaAdapter
from samuel.core.ports import IVersionControl
from samuel.core.types import PR, Comment, Issue, Label


@pytest.fixture
def auth():
    return StaticTokenAuth("test-token")


@pytest.fixture
def adapter(auth):
    return GiteaAdapter("http://gitea.local", "owner/repo", auth)


ISSUE_DATA = {
    "number": 42,
    "title": "Test issue",
    "body": "Some body",
    "state": "open",
    "labels": [{"id": 1, "name": "bug"}],
}

COMMENT_DATA = {
    "id": 100,
    "body": "A comment",
    "user": {"login": "bot"},
    "created_at": "2026-01-01T00:00:00Z",
}

PR_DATA = {
    "id": 5,
    "number": 10,
    "title": "My PR",
    "html_url": "http://gitea.local/owner/repo/pulls/10",
    "state": "open",
    "merged": False,
}

LABELS_DATA = [
    {"id": 1, "name": "bug"},
    {"id": 2, "name": "in-progress"},
    {"id": 3, "name": "done"},
]


class TestGiteaAdapterInterface:
    def test_implements_iversioncontrol(self, adapter):
        assert isinstance(adapter, IVersionControl)

    def test_capabilities(self, adapter):
        assert adapter.capabilities == {"labels", "webhooks_basic"}


class TestGetIssue:
    def test_returns_issue(self, adapter):
        with patch.object(adapter._api, "request", return_value=ISSUE_DATA):
            issue = adapter.get_issue(42)
        assert isinstance(issue, Issue)
        assert issue.number == 42
        assert issue.title == "Test issue"
        assert issue.labels == [Label(id=1, name="bug")]


class TestGetComments:
    def test_returns_comments(self, adapter):
        with patch.object(adapter._api, "request", return_value=[COMMENT_DATA]):
            comments = adapter.get_comments(42)
        assert len(comments) == 1
        assert isinstance(comments[0], Comment)
        assert comments[0].user == "bot"

    def test_empty_comments(self, adapter):
        with patch.object(adapter._api, "request", return_value=[]):
            comments = adapter.get_comments(42)
        assert comments == []


class TestPostComment:
    def test_posts_and_returns(self, adapter):
        with patch.object(adapter._api, "request", return_value=COMMENT_DATA) as mock:
            comment = adapter.post_comment(42, "Hello")
        mock.assert_called_once_with(
            "POST", "/repos/owner/repo/issues/42/comments", {"body": "Hello"}
        )
        assert isinstance(comment, Comment)
        assert comment.body == "A comment"


class TestCreatePR:
    def test_creates_pr(self, adapter):
        with patch.object(adapter._api, "request", return_value=PR_DATA) as mock:
            pr = adapter.create_pr("feature", "main", "My PR", "Description")
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/pulls",
            {"title": "My PR", "body": "Description", "head": "feature", "base": "main"},
        )
        assert isinstance(pr, PR)
        assert pr.html_url == "http://gitea.local/owner/repo/pulls/10"


class TestSwapLabel:
    def test_removes_then_adds(self, adapter):
        calls = []

        def mock_request(method, path, data=None):
            calls.append((method, path, data))
            if path.endswith("/labels") and method == "GET":
                return LABELS_DATA
            return None

        with patch.object(adapter._api, "request", side_effect=mock_request):
            adapter.swap_label(42, "bug", "done")

        assert calls[0] == ("GET", "/repos/owner/repo/labels", None)
        assert calls[1] == ("DELETE", "/repos/owner/repo/issues/42/labels/1", None)
        assert calls[2] == (
            "POST",
            "/repos/owner/repo/issues/42/labels",
            {"labels": [3]},
        )


class TestListLabels:
    def test_returns_labels(self, adapter):
        with patch.object(adapter._api, "request", return_value=[
            {"id": 1, "name": "bug", "color": "ff0000", "description": "buggy"},
            {"id": 2, "name": "docs", "color": "00ff00"},
        ]):
            labels = adapter.list_labels()
        assert len(labels) == 2
        assert labels[0] == {"id": 1, "name": "bug", "color": "ff0000", "description": "buggy"}
        assert labels[1]["description"] == ""


class TestCreateLabel:
    def test_creates_and_invalidates_cache(self, adapter):
        adapter._label_cache = {"existing": 1}
        with patch.object(adapter._api, "request", return_value={
            "id": 99, "name": "new-label", "color": "abcdef", "description": "x",
        }) as mock:
            result = adapter.create_label("new-label", "abcdef", "x")

        mock.assert_called_once_with(
            "POST", "/repos/owner/repo/labels",
            {"name": "new-label", "color": "abcdef", "description": "x"},
        )
        assert result == {"id": 99, "name": "new-label", "color": "abcdef", "description": "x"}
        assert adapter._label_cache is None


class TestListIssues:
    def test_returns_issues(self, adapter):
        with patch.object(adapter._api, "request", return_value=[ISSUE_DATA]):
            issues = adapter.list_issues(["bug"])
        assert len(issues) == 1
        assert issues[0].number == 42


class TestCloseIssue:
    def test_closes(self, adapter):
        with patch.object(adapter._api, "request", return_value=None) as mock:
            adapter.close_issue(42)
        mock.assert_called_once_with(
            "PATCH", "/repos/owner/repo/issues/42", {"state": "closed"}
        )


class TestMergePR:
    def test_merges(self, adapter):
        with patch.object(adapter._api, "request", return_value=None) as mock:
            result = adapter.merge_pr(10)
        assert result is True
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/pulls/10/merge",
            {"Do": "merge", "delete_branch_after_merge": True},
        )


class TestURLMethods:
    def test_issue_url(self, adapter):
        assert adapter.issue_url(42) == "http://gitea.local/owner/repo/issues/42"

    def test_pr_url(self, adapter):
        assert adapter.pr_url(10) == "http://gitea.local/owner/repo/pulls/10"

    def test_branch_url(self, adapter):
        assert adapter.branch_url("feat/x") == "http://gitea.local/owner/repo/src/branch/feat/x"


class TestAPIGuard:
    def test_blocks_hooks_write(self, adapter):
        with pytest.raises(PermissionError, match="API-Guard"):
            adapter._api.request("POST", "/repos/owner/repo/hooks")

    def test_allows_hooks_read(self, adapter):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"[]"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            adapter._api.request("GET", "/repos/owner/repo/hooks")
