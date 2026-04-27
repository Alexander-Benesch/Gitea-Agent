from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.factory import create_llm_adapter
from samuel.adapters.llm.lmstudio import LMStudioAdapter
from samuel.adapters.llm.ollama import OllamaAdapter
from samuel.adapters.llm.sanitizer import SanitizingLLMAdapter
from samuel.core.ports import IConfig, ILLMProvider, ISecretsProvider


def _make_config(provider: str = "ollama") -> MagicMock:
    config = MagicMock(spec=IConfig)
    config.get.side_effect = lambda key, default=None: {
        "llm.default.provider": provider,
    }.get(key, default)
    return config


def _make_secrets(**kv) -> MagicMock:
    secrets = MagicMock(spec=ISecretsProvider)
    secrets.get.side_effect = lambda key: kv.get(key, "test-key")
    return secrets


class TestFactory:
    def test_creates_ollama_by_default(self):
        adapter = create_llm_adapter(_make_config("ollama"), _make_secrets())
        assert isinstance(adapter, CircuitBreakerAdapter)
        assert isinstance(adapter._inner, SanitizingLLMAdapter)
        assert isinstance(adapter._inner._inner, OllamaAdapter)

    def test_creates_claude(self):
        adapter = create_llm_adapter(
            _make_config("claude"), _make_secrets(ANTHROPIC_API_KEY="sk-123")
        )
        assert isinstance(adapter._inner._inner, ClaudeAdapter)

    def test_creates_deepseek(self):
        adapter = create_llm_adapter(
            _make_config("deepseek"), _make_secrets(DEEPSEEK_API_KEY="dk-123")
        )
        assert isinstance(adapter._inner._inner, DeepSeekAdapter)

    def test_creates_lmstudio(self):
        adapter = create_llm_adapter(_make_config("lmstudio"), _make_secrets())
        assert isinstance(adapter._inner._inner, LMStudioAdapter)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider 'foo'"):
            create_llm_adapter(_make_config("foo"), _make_secrets())

    def test_returns_illmprovider(self):
        adapter = create_llm_adapter(_make_config(), _make_secrets())
        assert isinstance(adapter, ILLMProvider)

    def test_wraps_with_sanitizer_and_circuit_breaker(self):
        adapter = create_llm_adapter(_make_config("claude"), _make_secrets())
        assert isinstance(adapter, CircuitBreakerAdapter)
        assert isinstance(adapter._inner, SanitizingLLMAdapter)
