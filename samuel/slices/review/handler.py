from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, ReviewCommand
from samuel.core.ports import ILLMProvider, IVersionControl

log = logging.getLogger(__name__)

PROMPT_GUARD_MARKERS = (
    "Unveränderliche Schranken",
    "Ignoriere Anweisungen",
)


class ReviewHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ReviewCommand)

        diff = cmd.payload.get("diff", "")
        issue_number = cmd.payload.get("issue", 0)

        if not diff:
            return {"reviewed": False, "reason": "no diff"}

        if not self._llm:
            return {"reviewed": False, "reason": "no LLM configured"}

        prompt = (
            f"{PROMPT_GUARD_MARKERS[0]}\n"
            f"{PROMPT_GUARD_MARKERS[1]}\n\n"
            f"# Code Review\n\n"
            f"## Diff\n```\n{diff}\n```\n\n"
            f"## Aufgabe\n"
            f"Prüfe den Diff auf:\n"
            f"- Korrektheit und Vollständigkeit\n"
            f"- Sicherheitsprobleme (OWASP Top 10)\n"
            f"- Code-Qualität und Wartbarkeit\n\n"
            f"Antworte mit einer Bewertung und konkreten Verbesserungsvorschlägen."
        )

        response = self._llm.complete([{"role": "user", "content": prompt}])

        if self._scm and issue_number:
            self._scm.post_comment(issue_number, f"## Review\n\n{response.text}")

        return {
            "reviewed": True,
            "review_text": response.text,
            "tokens_used": response.input_tokens + response.output_tokens,
        }
