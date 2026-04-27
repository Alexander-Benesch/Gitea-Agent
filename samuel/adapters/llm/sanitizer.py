from __future__ import annotations

from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse, strip_html
from samuel.slices.privacy.handler import PromptSanitizer

MAX_RESPONSE_LENGTH = 100_000


class SanitizingLLMAdapter(ILLMProvider):
    def __init__(
        self, inner: ILLMProvider, *, pii_config: dict[str, Any] | None = None
    ):
        self._inner = inner
        self._sanitizer = PromptSanitizer(pii_config) if pii_config else None

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        if self._sanitizer:
            messages = self._sanitize_messages(messages)
        response = self._inner.complete(messages, **kwargs)
        response.text = strip_html(response.text)
        if len(response.text) > MAX_RESPONSE_LENGTH:
            response.text = response.text[:MAX_RESPONSE_LENGTH]
        return response

    def _sanitize_messages(self, messages: list[dict]) -> list[dict]:
        sanitized = []
        for msg in messages:
            content = msg.get("content", "")
            if content and msg.get("role") == "user":
                content, _ = self._sanitizer.sanitize(content)
            sanitized.append({**msg, "content": content})
        return sanitized

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)
