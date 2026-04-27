from __future__ import annotations

from unittest.mock import patch

from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.lmstudio import LMStudioAdapter
from samuel.adapters.llm.ollama import OllamaAdapter
from samuel.adapters.llm.openai_compat import OpenAICompatAdapter
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

CLAUDE_RESPONSE = {
    "content": [{"text": "Hello world"}],
    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3},
    "stop_reason": "end_turn",
    "model": "claude-sonnet-4-6",
}

OPENAI_RESPONSE = {
    "choices": [{"message": {"content": "Hello world"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 2}},
    "model": "deepseek-chat",
}

OLLAMA_RESPONSE = {
    "response": "Hello world",
    "model": "llama3",
    "prompt_eval_count": 10,
    "eval_count": 5,
}

MESSAGES = [{"role": "user", "content": "hi"}]


class TestClaudeAdapter:
    def test_implements_interface(self):
        adapter = ClaudeAdapter(api_key="test")
        assert isinstance(adapter, ILLMProvider)

    def test_capabilities(self):
        adapter = ClaudeAdapter(api_key="test")
        assert "tool_use" in adapter.capabilities
        assert "streaming" in adapter.capabilities

    def test_context_window(self):
        adapter = ClaudeAdapter(api_key="test", model="claude-opus-4-6")
        assert adapter.context_window == 200_000

    @patch("samuel.adapters.llm.claude.http_post", return_value=CLAUDE_RESPONSE)
    def test_complete(self, mock_post):
        adapter = ClaudeAdapter(api_key="test-key")
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.cached_tokens == 3
        assert resp.model_used == "claude-sonnet-4-6"
        assert resp.latency_ms >= 0

    def test_estimate_tokens(self):
        adapter = ClaudeAdapter(api_key="test")
        assert adapter.estimate_tokens("hello world") > 0


class TestDeepSeekAdapter:
    def test_implements_interface(self):
        assert isinstance(DeepSeekAdapter(api_key="test"), ILLMProvider)

    @patch("samuel.adapters.llm.openai_compat.http_post", return_value=OPENAI_RESPONSE)
    def test_complete(self, mock_post):
        adapter = DeepSeekAdapter(api_key="test-key")
        resp = adapter.complete(MESSAGES)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.cached_tokens == 2

    def test_context_window(self):
        assert DeepSeekAdapter(api_key="test").context_window == 128_000


class TestOllamaAdapter:
    def test_implements_interface(self):
        assert isinstance(OllamaAdapter(), ILLMProvider)

    @patch("samuel.adapters.llm.ollama.http_post", return_value=OLLAMA_RESPONSE)
    def test_complete(self, mock_post):
        adapter = OllamaAdapter(model="llama3")
        resp = adapter.complete(MESSAGES)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.model_used == "llama3"

    def test_capabilities_empty(self):
        assert OllamaAdapter().capabilities == set()


class TestLMStudioAdapter:
    def test_implements_interface(self):
        assert isinstance(LMStudioAdapter(), ILLMProvider)

    def test_context_window(self):
        assert LMStudioAdapter().context_window == 32_000


class TestOpenAICompatAdapter:
    @patch("samuel.adapters.llm.openai_compat.http_post", return_value=OPENAI_RESPONSE)
    def test_complete(self, mock_post):
        adapter = OpenAICompatAdapter(
            api_key="key", base_url="http://api.example.com/v1", model="gpt-4o"
        )
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"
