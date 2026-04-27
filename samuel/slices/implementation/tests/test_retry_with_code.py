from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from samuel.core.types import LLMResponse
from samuel.slices.implementation.llm_loop import (
    _build_retry_prompt,
    _load_file_excerpt_for_patch,
    run_llm_loop,
)


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.context_window = 32000

    def complete(self, messages: list[dict], **_: Any) -> LLMResponse:
        self.prompts.append(messages[-1]["content"])
        text = self._responses.pop(0) if self._responses else ""
        return LLMResponse(text=text, input_tokens=10, output_tokens=20, stop_reason="end")

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4


@dataclass
class _P:
    file: str
    lines: tuple[int, int] | None = None
    search: str | None = None
    type: str | None = None


class TestLoadExcerpt:
    def test_replace_lines_loads_context(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("\n".join(f"line{i}" for i in range(40)))
        excerpt = _load_file_excerpt_for_patch(tmp_path, {
            "file": "a.py", "lines": (20, 22), "type": "replace_lines",
        })
        assert "line15" in excerpt
        assert "line20" in excerpt
        assert "line30" in excerpt

    def test_search_anchors_to_hit(self, tmp_path: Path) -> None:
        content = "\n".join(["pre"] * 15 + ["target_line"] + ["post"] * 15)
        (tmp_path / "a.py").write_text(content)
        excerpt = _load_file_excerpt_for_patch(tmp_path, {
            "file": "a.py", "search": "target_line", "replace": "x",
        })
        assert "target_line" in excerpt

    def test_missing_file_returns_note(self, tmp_path: Path) -> None:
        excerpt = _load_file_excerpt_for_patch(tmp_path, {"file": "nope.py"})
        assert "existiert nicht" in excerpt


class TestBuildRetryPrompt:
    def test_includes_failure_and_code(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        prompt = _build_retry_prompt(
            base_prompt="Base task",
            round_num=1,
            failures_with_patches=[("SEARCH not found in mod.py", {"file": "mod.py", "search": "def foo"})],
            project_root=tmp_path,
        )
        assert "Base task" in prompt
        assert "SEARCH not found" in prompt
        assert "mod.py" in prompt
        assert "def foo" in prompt

    def test_deduplicates_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")
        prompt = _build_retry_prompt(
            base_prompt="B",
            round_num=1,
            failures_with_patches=[
                ("fail1", {"file": "a.py", "search": "x"}),
                ("fail2", {"file": "a.py", "search": "x"}),
            ],
            project_root=tmp_path,
        )
        assert prompt.count("a.py (aktueller Zustand)") == 1


class TestLoopRetriesWithRealCode:
    def test_retry_includes_real_code_on_failure(self, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("def existing():\n    return 1\n")
        bad_patch = (
            "## f.py\n"
            "<<<<<<< SEARCH\n"
            "def nonexistent():\n"
            "=======\n"
            "def replaced():\n"
            ">>>>>>> REPLACE\n"
        )
        good_patch = (
            "## f.py\n"
            "<<<<<<< SEARCH\n"
            "def existing():\n"
            "    return 1\n"
            "=======\n"
            "def existing():\n"
            "    return 2\n"
            ">>>>>>> REPLACE\n"
        )
        llm = ScriptedLLM([bad_patch, good_patch])

        result = run_llm_loop(llm, "base prompt", project_root=tmp_path)

        assert result["success"] is True
        assert result["round"] == 2
        assert any("aktueller Zustand" in p for p in llm.prompts[1:])
        assert any("def existing()" in p for p in llm.prompts[1:])

    def test_loop_returns_failure_if_still_fails(self, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("x = 1\n")
        bad = (
            "## f.py\n"
            "<<<<<<< SEARCH\n"
            "not-there\n"
            "=======\n"
            "replacement\n"
            ">>>>>>> REPLACE\n"
        )
        llm = ScriptedLLM([bad] * 5)

        result = run_llm_loop(llm, "base", project_root=tmp_path)

        assert result["success"] is False
        assert result["reason"] == "partial_failure"
        assert len(result["failures"]) >= 1
