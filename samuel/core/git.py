"""Git operations for S.A.M.U.E.L. v2 — branch, commit, push."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT = 30


def _run(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    """Run a git command, return (success, output)."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=str(cwd) if cwd else None,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            log.warning("git %s failed: %s", " ".join(args[:2]), result.stderr.strip())
            return False, result.stderr.strip()
        return True, output
    except subprocess.TimeoutExpired:
        log.error("git %s timed out", " ".join(args[:2]))
        return False, "timeout"
    except FileNotFoundError:
        log.error("git not found")
        return False, "git not found"


def current_branch(cwd: Path | None = None) -> str:
    """Return the name of the current branch."""
    ok, out = _run(["branch", "--show-current"], cwd)
    return out if ok else ""


def create_branch(name: str, base: str = "main", cwd: Path | None = None) -> bool:
    """Create and checkout a new branch from origin/<base>."""
    _run(["fetch", "origin", base], cwd)
    ok, _ = _run(["checkout", "-b", name, f"origin/{base}"], cwd)
    if not ok:
        # Branch might already exist, try checkout
        ok, _ = _run(["checkout", name], cwd)
    return ok


def stage_files(files: list[str], cwd: Path | None = None) -> bool:
    """Stage files for commit. Empty list stages all changes."""
    if not files:
        ok, _ = _run(["add", "-A"], cwd)
        return ok
    ok, _ = _run(["add", "--", *files], cwd)
    return ok


def commit(message: str, cwd: Path | None = None) -> bool:
    """Create a commit with the given message."""
    ok, _ = _run(["commit", "-m", message], cwd)
    return ok


def push(branch: str, cwd: Path | None = None) -> bool:
    """Push branch to origin."""
    ok, _ = _run(["push", "-u", "origin", branch], cwd)
    return ok


def checkout(branch: str, cwd: Path | None = None) -> bool:
    """Checkout an existing branch."""
    ok, _ = _run(["checkout", branch], cwd)
    return ok


def changed_files(base: str = "main", cwd: Path | None = None) -> list[str]:
    """List files changed between origin/<base> and HEAD."""
    ok, out = _run(["diff", "--name-only", f"origin/{base}...HEAD"], cwd)
    if ok and out:
        return [f for f in out.split("\n") if f]
    return []


def diff_text(base: str = "main", cwd: Path | None = None) -> str:
    """Return the diff text between origin/<base> and HEAD."""
    ok, out = _run(["diff", f"origin/{base}...HEAD"], cwd)
    return out if ok else ""
