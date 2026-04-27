from __future__ import annotations

from samuel.adapters.llm.openai_compat import OpenAICompatAdapter


class DeepSeekAdapter(OpenAICompatAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            model=model,
            context_window=128_000,
            max_tokens=max_tokens,
            timeout=timeout,
        )
