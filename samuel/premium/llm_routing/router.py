from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from samuel.core.ports import IConfig, ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)

TASK_COMPLEXITY = {
    "plan": "complex",
    "implement": "complex",
    "review": "complex",
    "eval": "simple",
    "heal": "complex",
    "changelog": "simple",
    "health": "simple",
}

NIGHT_HOURS = range(0, 7)


class RoutingLLMProvider(ILLMProvider):
    def __init__(
        self,
        providers: dict[str, ILLMProvider],
        config: IConfig | None = None,
        default_provider: str = "ollama",
    ) -> None:
        self._providers = providers
        self._config = config
        self._default = default_provider

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        task_type = kwargs.pop("task_type", "")
        provider = self._select_provider(task_type)
        return provider.complete(messages, **kwargs)

    def estimate_tokens(self, text: str) -> int:
        provider = self._providers.get(self._default)
        if provider:
            return provider.estimate_tokens(text)
        return len(text) // 4

    @property
    def context_window(self) -> int:
        provider = self._providers.get(self._default)
        return provider.context_window if provider else 200_000

    @property
    def capabilities(self) -> set[str]:
        provider = self._providers.get(self._default)
        return provider.capabilities if provider else set()

    def _select_provider(self, task_type: str) -> ILLMProvider:
        complexity = TASK_COMPLEXITY.get(task_type, "complex")
        is_night = datetime.now(timezone.utc).hour in NIGHT_HOURS

        if is_night and self._config:
            night_provider = self._config.get("llm.routing.night_provider")
            if night_provider and night_provider in self._providers:
                return self._providers[night_provider]

        if complexity == "simple":
            for name in ["ollama", "lmstudio", "deepseek"]:
                if name in self._providers:
                    return self._providers[name]

        for name in ["claude", "openai", "deepseek"]:
            if name in self._providers:
                return self._providers[name]

        return next(iter(self._providers.values()))
