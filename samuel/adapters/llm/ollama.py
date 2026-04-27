from __future__ import annotations

import time

from samuel.adapters.llm.http import http_post
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class OllamaAdapter(ILLMProvider):
    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def context_window(self) -> int:
        return 128_000

    @property
    def capabilities(self) -> set[str]:
        return set()

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        prompt = "\n".join(m.get("content", "") for m in messages)
        payload = {
            "model": kwargs.get("model", self._model),
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.2),
                "num_predict": kwargs.get("max_tokens", self._max_tokens),
            },
        }
        if system := kwargs.get("system"):
            payload["system"] = system

        t0 = time.monotonic()
        result = http_post(
            f"{self._base_url}/api/generate",
            payload,
            {"Content-Type": "application/json"},
            self._timeout,
        )
        latency = int((time.monotonic() - t0) * 1000)

        return LLMResponse(
            text=result.get("response", "").strip(),
            input_tokens=result.get("prompt_eval_count", 0),
            output_tokens=result.get("eval_count", 0),
            model_used=result.get("model", self._model),
            latency_ms=latency,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
