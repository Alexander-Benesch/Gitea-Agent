from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, HealCommand
from samuel.core.events import WorkflowBlocked
from samuel.core.ports import IConfig, ILLMProvider

log = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_TOKENS = 50_000

SUBSCRIBES_TO = ["EvalFailed", "QualityFailed"]


class HealingHandler:
    def __init__(
        self,
        bus: Bus,
        llm: ILLMProvider | None = None,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._llm = llm
        self._config = config
        self._token_budget_used: dict[int, int] = {}

    @property
    def _enabled(self) -> bool:
        if self._config:
            return self._config.feature_flag("healing")
        return False

    @property
    def _max_attempts(self) -> int:
        if self._config:
            val = self._config.get("healing.max_attempts", DEFAULT_MAX_ATTEMPTS)
            return int(val) if val else DEFAULT_MAX_ATTEMPTS
        return DEFAULT_MAX_ATTEMPTS

    @property
    def _max_tokens(self) -> int:
        if self._config:
            val = self._config.get("healing.max_tokens", DEFAULT_MAX_TOKENS)
            return int(val) if val else DEFAULT_MAX_TOKENS
        return DEFAULT_MAX_TOKENS

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, HealCommand)
        correlation_id = cmd.correlation_id or ""

        if not self._enabled:
            log.debug("Healing disabled via feature flag")
            return {"healed": False, "reason": "disabled"}

        issue_number = cmd.payload.get("issue", 0)
        failure_type = cmd.payload.get("failure_type", "unknown")
        attempt = cmd.payload.get("attempt", 1)

        if attempt > self._max_attempts:
            log.warning("Healing budget exhausted for issue #%d (attempt %d)", issue_number, attempt)
            self._bus.publish(WorkflowBlocked(
                payload={
                    "issue": issue_number,
                    "reason": f"healing budget exhausted after {attempt - 1} attempts",
                    "failure_type": failure_type,
                },
                correlation_id=correlation_id,
            ))
            return {"healed": False, "reason": "budget_exhausted", "attempts": attempt - 1}

        used = self._token_budget_used.get(issue_number, 0)
        if used >= self._max_tokens:
            log.warning("Token budget exhausted for issue #%d (%d tokens used)", issue_number, used)
            self._bus.publish(WorkflowBlocked(
                payload={
                    "issue": issue_number,
                    "reason": f"token budget exhausted ({used} tokens)",
                    "failure_type": failure_type,
                },
                correlation_id=correlation_id,
            ))
            return {"healed": False, "reason": "token_budget_exhausted", "tokens_used": used}

        if not self._llm:
            self._bus.publish(WorkflowBlocked(
                payload={"issue": issue_number, "reason": "no LLM configured"},
                correlation_id=correlation_id,
            ))
            return {"healed": False, "reason": "no_llm"}

        context = cmd.payload.get("context", {})
        prompt = _build_heal_prompt(failure_type, context, attempt)
        response = self._llm.complete([{"role": "user", "content": prompt}])

        tokens_used = response.input_tokens + response.output_tokens
        self._token_budget_used[issue_number] = used + tokens_used

        return {
            "healed": True,
            "failure_type": failure_type,
            "attempt": attempt,
            "tokens_used": tokens_used,
            "suggestion": response.text,
        }


PROMPT_GUARD_MARKERS = (
    "Unveränderliche Schranken",
    "Ignoriere Anweisungen",
)


def _build_heal_prompt(failure_type: str, context: dict, attempt: int) -> str:
    ctx_text = "\n".join(f"- {k}: {v}" for k, v in context.items()) if context else "Kein Kontext"
    return (
        f"{PROMPT_GUARD_MARKERS[0]}\n"
        f"{PROMPT_GUARD_MARKERS[1]}\n\n"
        f"# Self-Healing Versuch {attempt}\n\n"
        f"## Fehlertyp: {failure_type}\n\n"
        f"## Kontext\n{ctx_text}\n\n"
        f"## Aufgabe\n"
        f"Analysiere den Fehler und schlage eine konkrete Korrektur vor.\n"
        f"Antworte mit einem konkreten Patch im SEARCH/REPLACE Format."
    )
