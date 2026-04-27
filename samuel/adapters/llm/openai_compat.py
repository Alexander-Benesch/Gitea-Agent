from __future__ import annotations

import time

from samuel.adapters.llm.http import http_post
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class OpenAICompatAdapter(ILLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        context_window: int = 128_000,
        max_tokens: int = 4096,
        timeout: int = 120,
        provider_caps: set[str] | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._context_window = context_window
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._caps = provider_caps or set()

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def capabilities(self) -> set[str]:
        return self._caps

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        payload = {
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
        }

        t0 = time.monotonic()
        result = http_post(
            f"{self._base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            self._timeout,
        )
        latency = int((time.monotonic() - t0) * 1000)

        text = result["choices"][0]["message"]["content"].strip()
        usage = result.get("usage", {})
        return LLMResponse(
            text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cached_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            stop_reason=result["choices"][0].get("finish_reason", "stop"),
            model_used=result.get("model", self._model),
            latency_ms=latency,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
