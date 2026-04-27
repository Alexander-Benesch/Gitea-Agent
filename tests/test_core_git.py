"""Tests for samuel.core.git — subprocess-based git operations."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from samuel.core.git import (
    _run,
    changed_files,
    checkout,
    commit,
    create_branch,
    current_branch,
    diff_text,
    push,
    stage_files,
)


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock subprocess.run result."""
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


class TestRun:
    def test_success(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="ok\n")) as mock:
            ok, out = _run(["status"])
            assert ok is True
            assert out == "ok"
            mock.assert_called_once()

    def test_failure(self):
        with patch("subprocess.run", return_value=_mock_run(stderr="error", returncode=1)):
            ok, out = _run(["checkout", "nonexistent"])
            assert ok is False
            assert out == "error"

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            ok, out = _run(["log"])
            assert ok is False
            assert out == "timeout"

    def test_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, out = _run(["status"])
            assert ok is False
            assert out == "git not found"

    def test_cwd_passed(self, tmp_path: Path):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            _run(["status"], cwd=tmp_path)
            assert mock.call_args[1]["cwd"] == str(tmp_path)


class TestCurrentBranch:
    def test_returns_branch_name(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="main\n")):
            assert current_branch() == "main"

    def test_empty_on_failure(self):
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stderr="err")):
            assert current_branch() == ""


class TestCreateBranch:
    def test_creates_new_branch(self):
        calls = []

        def mock_run(args, **kwargs):
            calls.append(args)
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            ok = create_branch("feat/x", "main")
            assert ok is True
            assert ["git", "fetch", "origin", "main"] in calls
            assert ["git", "checkout", "-b", "feat/x", "origin/main"] in calls

    def test_falls_back_to_checkout_if_exists(self):
        call_count = [0]

        def mock_run(args, **kwargs):
            call_count[0] += 1
            if args == ["git", "checkout", "-b", "feat/x", "origin/main"]:
                return _mock_run(returncode=1, stderr="already exists")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            ok = create_branch("feat/x", "main")
            assert ok is True


class TestStageFiles:
    def test_stage_all(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = stage_files([])
            assert ok is True
            assert mock.call_args[0][0] == ["git", "add", "-A"]

    def test_stage_specific_files(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = stage_files(["a.py", "b.py"])
            assert ok is True
            assert mock.call_args[0][0] == ["git", "add", "--", "a.py", "b.py"]


class TestCommit:
    def test_commit_message(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = commit("fix: stuff")
            assert ok is True
            assert mock.call_args[0][0] == ["git", "commit", "-m", "fix: stuff"]


class TestPush:
    def test_push_branch(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = push("feat/x")
            assert ok is True
            assert mock.call_args[0][0] == ["git", "push", "-u", "origin", "feat/x"]


class TestCheckout:
    def test_checkout_branch(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = checkout("main")
            assert ok is True
            assert mock.call_args[0][0] == ["git", "checkout", "main"]


class TestChangedFiles:
    def test_returns_file_list(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="a.py\nb.py\n")):
            files = changed_files("main")
            assert files == ["a.py", "b.py"]

    def test_empty_on_no_changes(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="")):
            assert changed_files() == []

    def test_empty_on_failure(self):
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stderr="err")):
            assert changed_files() == []


class TestDiffText:
    def test_returns_diff(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="diff --git ...")):
            assert diff_text() == "diff --git ..."

    def test_empty_on_failure(self):
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stderr="err")):
            assert diff_text() == ""
