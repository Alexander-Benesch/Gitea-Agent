from __future__ import annotations

from samuel.adapters.llm.costs import estimate_cost


class TestEstimateCost:
    def test_local_providers_free(self):
        assert estimate_cost("ollama", "llama3", input_tokens=1000, output_tokens=500) == 0.0
        assert estimate_cost("lmstudio", "model", input_tokens=1000, output_tokens=500) == 0.0

    def test_zero_tokens(self):
        assert estimate_cost("claude", "claude-sonnet-4-6", input_tokens=0, output_tokens=0) == 0.0

    def test_hardcoded_fallback(self):
        cost = estimate_cost("claude", "claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
        assert cost > 0
        expected = 3.0 * 1500 / 1_000_000
        assert abs(cost - expected) < 1e-6

    def test_cached_tokens_reduce_cost(self):
        full = estimate_cost("claude", "claude-opus-4-6", input_tokens=1000, output_tokens=500)
        assert full > 0

    def test_unknown_provider_fallback(self):
        cost = estimate_cost("unknown", "model", input_tokens=1000, output_tokens=500)
        assert cost == 0.0

    def test_deepseek_cost(self):
        cost = estimate_cost("deepseek", "deepseek-chat", input_tokens=10000, output_tokens=5000)
        expected = 0.14 * 15000 / 1_000_000
        assert abs(cost - expected) < 1e-6
