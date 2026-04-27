"""Tests for premium LLM routing."""
from __future__ import annotations

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse
from samuel.premium.llm_routing.handler import create_routing_provider
from samuel.premium.llm_routing.router import TASK_COMPLEXITY, RoutingLLMProvider

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockLLM(ILLMProvider):
    def __init__(self, name: str = "mock") -> None:
        self.name = name
        self.calls: list = []

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(text=f"from {self.name}", input_tokens=10, output_tokens=5)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class MockConfig:
    def __init__(self, values: dict | None = None) -> None:
        self._v = values or {}

    def get(self, key: str, default=None):
        return self._v.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests: RoutingLLMProvider
# ---------------------------------------------------------------------------


class TestRoutingLLMProvider:
    """Tests for the RoutingLLMProvider selection logic."""

    def test_selects_complex_provider_for_plan(self):
        """Complex tasks (plan) should prefer claude > openai > deepseek."""
        claude = MockLLM("claude")
        ollama = MockLLM("ollama")
        router = RoutingLLMProvider({"claude": claude, "ollama": ollama})

        resp = router.complete([{"role": "user", "content": "hi"}], task_type="plan")

        assert resp.text == "from claude"
        assert len(claude.calls) == 1
        assert len(ollama.calls) == 0

    def test_selects_simple_provider_for_eval(self):
        """Simple tasks (eval) should prefer ollama > lmstudio > deepseek."""
        claude = MockLLM("claude")
        ollama = MockLLM("ollama")
        router = RoutingLLMProvider({"claude": claude, "ollama": ollama})

        resp = router.complete([{"role": "user", "content": "hi"}], task_type="eval")

        assert resp.text == "from ollama"
        assert len(ollama.calls) == 1
        assert len(claude.calls) == 0

    def test_falls_back_to_available_provider(self):
        """If no preferred provider exists, fall back to first available."""
        custom = MockLLM("custom")
        router = RoutingLLMProvider({"custom": custom})

        resp = router.complete([{"role": "user", "content": "hi"}], task_type="plan")

        assert resp.text == "from custom"
        assert len(custom.calls) == 1

    def test_simple_task_falls_back_to_complex_chain(self):
        """If no simple providers exist, simple tasks fall through to complex chain."""
        openai = MockLLM("openai")
        router = RoutingLLMProvider({"openai": openai})

        resp = router.complete([{"role": "user", "content": "hi"}], task_type="eval")

        assert resp.text == "from openai"

    def test_estimate_tokens_uses_default_provider(self):
        ollama = MockLLM("ollama")
        claude = MockLLM("claude")
        router = RoutingLLMProvider(
            {"claude": claude, "ollama": ollama}, default_provider="ollama"
        )

        result = router.estimate_tokens("hello world test")
        assert result == len("hello world test") // 4

    def test_context_window_uses_default_provider(self):
        ollama = MockLLM("ollama")
        router = RoutingLLMProvider({"ollama": ollama}, default_provider="ollama")

        assert router.context_window == 200_000

    def test_context_window_fallback_without_default(self):
        router = RoutingLLMProvider({"claude": MockLLM("claude")}, default_provider="missing")
        assert router.context_window == 200_000

    def test_task_complexity_mapping(self):
        """Verify known task types have expected complexities."""
        assert TASK_COMPLEXITY["plan"] == "complex"
        assert TASK_COMPLEXITY["implement"] == "complex"
        assert TASK_COMPLEXITY["eval"] == "simple"
        assert TASK_COMPLEXITY["changelog"] == "simple"
        assert TASK_COMPLEXITY["health"] == "simple"

    def test_unknown_task_defaults_to_complex(self):
        """Unknown task types should be treated as complex."""
        claude = MockLLM("claude")
        ollama = MockLLM("ollama")
        router = RoutingLLMProvider({"claude": claude, "ollama": ollama})

        resp = router.complete([{"role": "user", "content": "x"}], task_type="unknown_task")

        assert resp.text == "from claude"


# ---------------------------------------------------------------------------
# Tests: create_routing_provider factory
# ---------------------------------------------------------------------------


class TestCreateRoutingProvider:
    """Tests for the create_routing_provider() factory function."""

    def test_factory_returns_routing_provider(self):
        providers = {"claude": MockLLM("claude"), "ollama": MockLLM("ollama")}
        router = create_routing_provider(providers)

        assert isinstance(router, RoutingLLMProvider)

    def test_factory_respects_config_default(self):
        config = MockConfig({"llm.routing.default_provider": "claude"})
        providers = {"claude": MockLLM("claude"), "ollama": MockLLM("ollama")}
        router = create_routing_provider(providers, config=config)

        assert router._default == "claude"

    def test_factory_defaults_to_ollama_without_config(self):
        providers = {"claude": MockLLM("claude"), "ollama": MockLLM("ollama")}
        router = create_routing_provider(providers)

        assert router._default == "ollama"

    def test_factory_with_none_config(self):
        providers = {"ollama": MockLLM("ollama")}
        router = create_routing_provider(providers, config=None)

        assert isinstance(router, RoutingLLMProvider)
        assert router._default == "ollama"
