from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import ReviewCommand
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import PR, Comment, Issue, LLMResponse
from samuel.slices.review.handler import ReviewHandler


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


class MockLLM(ILLMProvider):
    def __init__(self, text: str = "LGTM") -> None:
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class TestReviewHandler:
    def test_review_with_diff(self) -> None:
        bus = Bus()
        handler = ReviewHandler(bus, llm=MockLLM("All good"))
        cmd = ReviewCommand(payload={"diff": "--- a/f.py\n+++ b/f.py\n+pass", "issue": 10})

        result = handler.handle(cmd)

        assert result["reviewed"] is True
        assert result["review_text"] == "All good"
        assert result["tokens_used"] == 150

    def test_no_diff_returns_not_reviewed(self) -> None:
        bus = Bus()
        handler = ReviewHandler(bus, llm=MockLLM())
        cmd = ReviewCommand(payload={"diff": "", "issue": 10})

        result = handler.handle(cmd)

        assert result["reviewed"] is False
        assert result["reason"] == "no diff"

    def test_no_llm_returns_not_reviewed(self) -> None:
        bus = Bus()
        handler = ReviewHandler(bus, llm=None)
        cmd = ReviewCommand(payload={"diff": "some diff", "issue": 10})

        result = handler.handle(cmd)

        assert result["reviewed"] is False
        assert result["reason"] == "no LLM configured"

    def test_posts_review_to_issue(self) -> None:
        bus = Bus()
        scm = MockSCM()
        handler = ReviewHandler(bus, scm=scm, llm=MockLLM("Needs fixes"))
        cmd = ReviewCommand(payload={"diff": "+new code", "issue": 42})

        result = handler.handle(cmd)

        assert result["reviewed"] is True
        assert len(scm.posted) == 1
        assert scm.posted[0][0] == 42
        assert "## Review" in scm.posted[0][1]
        assert "Needs fixes" in scm.posted[0][1]

    def test_no_post_without_scm(self) -> None:
        bus = Bus()
        handler = ReviewHandler(bus, scm=None, llm=MockLLM("OK"))
        cmd = ReviewCommand(payload={"diff": "+code", "issue": 5})

        result = handler.handle(cmd)

        assert result["reviewed"] is True
        assert result["review_text"] == "OK"

    def test_no_post_without_issue_number(self) -> None:
        bus = Bus()
        scm = MockSCM()
        handler = ReviewHandler(bus, scm=scm, llm=MockLLM("Fine"))
        cmd = ReviewCommand(payload={"diff": "+code"})

        result = handler.handle(cmd)

        assert result["reviewed"] is True
        assert len(scm.posted) == 0
