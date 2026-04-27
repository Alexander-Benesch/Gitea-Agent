from __future__ import annotations

from samuel.adapters.llm.openai_compat import OpenAICompatAdapter


class LMStudioAdapter(OpenAICompatAdapter):
    def __init__(
        self,
        model: str = "local-model",
        base_url: str = "http://localhost:1234/v1",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        super().__init__(
            api_key="lm-studio",
            base_url=base_url,
            model=model,
            context_window=32_000,
            max_tokens=max_tokens,
            timeout=timeout,
        )
