"""Contract tests for all Port interfaces (H1).

Each Port ABC gets a test that verifies the contract is implementable
and that our concrete adapters actually fulfill it.
"""
from __future__ import annotations

from pathlib import Path

from samuel.core.ports import (
    IAuthProvider,
    IQualityCheck,
    ISkeletonBuilder,
    IVersionControl,
)
from samuel.core.types import (
    SkeletonEntry,
)


class TestIVersionControlContract:
    def test_gitea_adapter_implements_all_methods(self):
        from samuel.adapters.gitea.adapter import GiteaAdapter

        assert issubclass(GiteaAdapter, IVersionControl)
        required = {
            "get_issue", "get_comments", "post_comment", "create_pr",
            "swap_label", "list_issues", "close_issue", "merge_pr",
            "issue_url", "pr_url", "branch_url", "capabilities",
        }
        actual = set(dir(GiteaAdapter))
        assert required.issubset(actual)

    def test_github_adapter_implements_all_methods(self):
        from samuel.adapters.github.adapter import GitHubAdapter

        assert issubclass(GitHubAdapter, IVersionControl)
        required = {
            "get_issue", "get_comments", "post_comment", "create_pr",
            "swap_label", "list_issues", "close_issue", "merge_pr",
            "issue_url", "pr_url", "branch_url", "capabilities",
        }
        actual = set(dir(GitHubAdapter))
        assert required.issubset(actual)


class TestIAuthProviderContract:
    def test_static_token_auth(self):
        from samuel.adapters.auth.static_token import StaticTokenAuth

        assert issubclass(StaticTokenAuth, IAuthProvider)
        auth = StaticTokenAuth("test-token")
        assert auth.get_token() == "test-token"
        assert auth.is_valid() is True

    def test_github_token_auth(self):
        from samuel.adapters.github.auth import GitHubTokenAuth

        assert issubclass(GitHubTokenAuth, IAuthProvider)
        auth = GitHubTokenAuth("ghp_test")
        assert auth.get_token() == "ghp_test"

    def test_github_app_auth(self):
        from samuel.adapters.github.auth import GitHubAppAuth

        assert issubclass(GitHubAppAuth, IAuthProvider)


class TestISkeletonBuilderContract:
    def test_python_builder(self, tmp_path: Path):
        from samuel.adapters.skeleton.python_ast import PythonASTBuilder

        assert issubclass(PythonASTBuilder, ISkeletonBuilder)
        b = PythonASTBuilder()
        assert ".py" in b.supported_extensions

        f = tmp_path / "test.py"
        f.write_text("def hello(): pass\n")
        entries = b.extract(f)
        assert all(isinstance(e, SkeletonEntry) for e in entries)

    def test_ts_builder(self, tmp_path: Path):
        from samuel.adapters.skeleton.tree_sitter_ts import TreeSitterTSBuilder

        assert issubclass(TreeSitterTSBuilder, ISkeletonBuilder)
        b = TreeSitterTSBuilder()
        assert ".ts" in b.supported_extensions

    def test_go_builder(self, tmp_path: Path):
        from samuel.adapters.skeleton.tree_sitter_go import GoRegexBuilder

        assert issubclass(GoRegexBuilder, ISkeletonBuilder)
        b = GoRegexBuilder()
        assert ".go" in b.supported_extensions

    def test_sql_builder(self):
        from samuel.adapters.skeleton.sql_builder import SQLBuilder

        assert issubclass(SQLBuilder, ISkeletonBuilder)

    def test_config_builder(self):
        from samuel.adapters.skeleton.config_builder import StructuredConfigBuilder

        assert issubclass(StructuredConfigBuilder, ISkeletonBuilder)


class TestIQualityCheckContract:
    def test_python_syntax_check(self, tmp_path: Path):
        from samuel.adapters.quality.checks import PythonSyntaxCheck

        assert issubclass(PythonSyntaxCheck, IQualityCheck)
        c = PythonSyntaxCheck()
        f = tmp_path / "ok.py"
        f.write_text("x = 1\n")
        result = c.run(f, f.read_text(), {})
        assert isinstance(result, dict)
        assert "passed" in result

    def test_scope_guard(self, tmp_path: Path):
        from samuel.adapters.quality.checks import ScopeGuard

        assert issubclass(ScopeGuard, IQualityCheck)
        c = ScopeGuard()
        assert "*" in c.supported_extensions
