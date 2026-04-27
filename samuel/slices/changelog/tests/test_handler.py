from __future__ import annotations

from samuel.core.bus import Bus
from samuel.core.commands import ChangelogCommand
from samuel.core.ports import IVersionControl
from samuel.core.types import PR, Comment, Issue
from samuel.slices.changelog.handler import ChangelogHandler


class MockSCM(IVersionControl):
    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="T", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class TestChangelogHandler:
    def test_generates_changelog(self) -> None:
        bus = Bus()
        handler = ChangelogHandler(bus)
        cmd = ChangelogCommand(payload={
            "entries": [
                {"issue": "10", "title": "Add login", "category": "feature"},
                {"issue": "11", "title": "Fix crash", "category": "fix"},
            ],
        })

        result = handler.handle(cmd)

        assert result["generated"] is True
        assert result["entry_count"] == 2
        assert "**feat:** Add login (#10)" in result["changelog"]
        assert "**fix:** Fix crash (#11)" in result["changelog"]

    def test_empty_entries_returns_not_generated(self) -> None:
        bus = Bus()
        handler = ChangelogHandler(bus)
        cmd = ChangelogCommand(payload={"entries": []})

        result = handler.handle(cmd)

        assert result["generated"] is False
        assert result["reason"] == "no entries"

    def test_no_entries_key_returns_not_generated(self) -> None:
        bus = Bus()
        handler = ChangelogHandler(bus)
        cmd = ChangelogCommand(payload={})

        result = handler.handle(cmd)

        assert result["generated"] is False

    def test_posts_to_issue_via_scm(self) -> None:
        bus = Bus()
        scm = MockSCM()
        handler = ChangelogHandler(bus, scm=scm)
        cmd = ChangelogCommand(payload={
            "entries": [{"issue": "5", "title": "New feature", "category": "feature"}],
            "post_to_issue": 42,
        })

        result = handler.handle(cmd)

        assert result["generated"] is True
        assert len(scm.posted) == 1
        assert scm.posted[0][0] == 42
        assert "# Changelog" in scm.posted[0][1]

    def test_no_post_without_scm(self) -> None:
        bus = Bus()
        handler = ChangelogHandler(bus, scm=None)
        cmd = ChangelogCommand(payload={
            "entries": [{"issue": "1", "title": "X", "category": "feature"}],
            "post_to_issue": 42,
        })

        result = handler.handle(cmd)

        assert result["generated"] is True

    def test_refactor_category(self) -> None:
        bus = Bus()
        handler = ChangelogHandler(bus)
        cmd = ChangelogCommand(payload={
            "entries": [{"issue": "3", "title": "Clean up", "category": "refactor"}],
        })

        result = handler.handle(cmd)

        assert "**refactor:** Clean up (#3)" in result["changelog"]
