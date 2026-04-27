from __future__ import annotations

import time

from samuel.adapters.llm.http import http_post
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

_CONTEXT_WINDOWS = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}


class ClaudeAdapter(ILLMProvider):
    BASE_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def context_window(self) -> int:
        return _CONTEXT_WINDOWS.get(self._model, 200_000)

    @property
    def capabilities(self) -> set[str]:
        return {"streaming", "tool_use", "structured_output"}

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        payload: dict = {
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", 0.2),
            "messages": messages,
        }
        if system := kwargs.get("system"):
            payload["system"] = system

        t0 = time.monotonic()
        result = http_post(
            self.BASE_URL,
            payload,
            {
                "x-api-key": self._api_key,
                "anthropic-version": self.API_VERSION,
                "content-type": "application/json",
            },
            self._timeout,
        )
        latency = int((time.monotonic() - t0) * 1000)

        text = result["content"][0]["text"].strip()
        usage = result.get("usage", {})
        return LLMResponse(
            text=text,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cache_read_input_tokens", 0),
            stop_reason=result.get("stop_reason", "end_turn"),
            model_used=result.get("model", self._model),
            latency_ms=latency,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
