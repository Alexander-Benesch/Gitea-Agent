from __future__ import annotations

from samuel.slices.implementation.context_validator import (
    MAX_PROMPT_TOKENS,
    MIN_PROMPT_TOKENS,
    WARN_PROMPT_TOKENS,
    validate_context,
)


def _make_context(skeleton="", relevant_files="", plan_files="", grep="", constraints="", keywords=""):
    return {
        "skeleton": skeleton,
        "relevant_files": relevant_files,
        "plan_files": plan_files,
        "grep": grep,
        "constraints": constraints,
        "keywords": keywords,
    }


class TestValidateContext:
    def test_empty_issue_title_fails(self) -> None:
        ctx = _make_context(skeleton="x" * 100)
        v = validate_context(
            issue_title="", issue_body="Some body that is long enough to pass",
            plan_text="", context=ctx, prompt="x" * 800,
        )
        assert not v.ok
        assert any("title" in i.lower() for i in v.issues)

    def test_too_short_body_fails(self) -> None:
        ctx = _make_context(skeleton="x" * 100)
        v = validate_context(
            issue_title="Title", issue_body="short",
            plan_text="", context=ctx, prompt="x" * 800,
        )
        assert not v.ok
        assert any("too short" in i.lower() for i in v.issues)

    def test_no_code_context_fails(self) -> None:
        ctx = _make_context()
        v = validate_context(
            issue_title="T", issue_body="A" * 50,
            plan_text="", context=ctx, prompt="x" * 1000,
        )
        assert not v.ok
        assert any("no code context" in i.lower() for i in v.issues)

    def test_no_concrete_files_warns(self) -> None:
        ctx = _make_context(skeleton="sym", grep="hit")
        v = validate_context(
            issue_title="T", issue_body="A" * 50,
            plan_text="", context=ctx, prompt="x" * 1000,
        )
        assert v.ok
        assert any("hallucinate" in w.lower() for w in v.warnings)

    def test_prompt_too_small_fails(self) -> None:
        ctx = _make_context(skeleton="x" * 100)
        v = validate_context(
            issue_title="T", issue_body="A" * 50,
            plan_text="", context=ctx, prompt="x" * (MIN_PROMPT_TOKENS - 10) * 4,
        )
        assert not v.ok
        assert any("too small" in i.lower() for i in v.issues)

    def test_prompt_too_large_fails(self) -> None:
        ctx = _make_context(skeleton="x" * 100, relevant_files="y" * 100)
        v = validate_context(
            issue_title="T", issue_body="A" * 50,
            plan_text="plan", context=ctx, prompt="x" * (MAX_PROMPT_TOKENS + 100) * 4,
        )
        assert not v.ok
        assert any("too large" in i.lower() for i in v.issues)

    def test_prompt_warning_zone(self) -> None:
        ctx = _make_context(skeleton="x" * 100, relevant_files="y" * 100)
        v = validate_context(
            issue_title="T", issue_body="A" * 50,
            plan_text="plan", context=ctx, prompt="x" * (WARN_PROMPT_TOKENS + 100) * 4,
        )
        assert v.ok
        assert any("large" in w.lower() for w in v.warnings)

    def test_happy_path(self) -> None:
        ctx = _make_context(
            skeleton="## Skeleton\n- foo L1-3",
            relevant_files="## File\ncode",
            plan_files="- file.py",
            grep="match",
            constraints="- rule",
            keywords="foo, bar",
        )
        v = validate_context(
            issue_title="Add foo", issue_body="This issue describes adding a foo feature",
            plan_text="Change file.py", context=ctx, prompt="x" * 5000,
        )
        assert v.ok
        assert v.issues == []
        assert v.prompt_tokens_est == 1250
        assert "relevant_files" in v.breakdown
