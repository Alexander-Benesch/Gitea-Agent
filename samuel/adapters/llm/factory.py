from __future__ import annotations

import json
import logging
from pathlib import Path

from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.costs import configure_cache_ttl
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.lmstudio import LMStudioAdapter
from samuel.adapters.llm.ollama import OllamaAdapter
from samuel.adapters.llm.sanitizer import SanitizingLLMAdapter
from samuel.core.ports import IConfig, ILLMProvider, ISecretsProvider

log = logging.getLogger(__name__)


def _load_llm_defaults(config_dir: str | Path = "config") -> dict:
    """Load LLM defaults from config/llm/defaults.json."""
    path = Path(config_dir) / "llm" / "defaults.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to load LLM defaults from %s: %s", path, exc)
    return {}


def create_llm_adapter(
    config: IConfig, secrets: ISecretsProvider
) -> ILLMProvider:
    provider = config.get("llm.default.provider", "ollama")
    config_dir = config.get("agent.config_dir", "config")
    llm_defaults = _load_llm_defaults(config_dir)

    # Apply pricing cache TTL from config
    pricing_cache_hours = llm_defaults.get("pricing_cache_hours")
    if pricing_cache_hours is not None:
        configure_cache_ttl(int(pricing_cache_hours))

    # Extract default LLM parameters
    default_params = llm_defaults.get("default", {})
    max_tokens = default_params.get("max_tokens", 4096)
    temperature = default_params.get("temperature", 0.2)

    # Extract circuit breaker config
    cb_config = llm_defaults.get("circuit_breaker", {})
    failure_threshold = cb_config.get("failure_threshold")
    cooldown_seconds = cb_config.get("cooldown_seconds")

    factories = {
        "claude": lambda: ClaudeAdapter(
            api_key=secrets.get("ANTHROPIC_API_KEY"),
            model=config.get("llm.claude.model", "claude-sonnet-4-6"),
        ),
        "deepseek": lambda: DeepSeekAdapter(
            api_key=secrets.get("DEEPSEEK_API_KEY"),
            model=config.get("llm.deepseek.model", "deepseek-chat"),
        ),
        "ollama": lambda: OllamaAdapter(
            model=config.get("llm.ollama.model", "llama3"),
            base_url=config.get("llm.ollama.url", "http://localhost:11434"),
        ),
        "lmstudio": lambda: LMStudioAdapter(
            model=config.get("llm.lmstudio.model", "local-model"),
            base_url=config.get("llm.lmstudio.url", "http://localhost:1234/v1"),
        ),
    }

    if provider not in factories:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Available: {', '.join(sorted(factories))}"
        )

    # Load PII scrubbing config
    pii_config = None
    try:
        privacy_path = Path(config_dir) / "privacy.json"
        if privacy_path.exists():
            privacy_data = json.loads(privacy_path.read_text(encoding="utf-8"))
            pii_config = privacy_data.get("pii_scrubbing")
    except Exception as e:
        log.warning("Failed to load PII scrubbing config: %s", e)

    inner = factories[provider]()
    adapter = CircuitBreakerAdapter(
        SanitizingLLMAdapter(inner, pii_config=pii_config),
        failure_threshold=failure_threshold,
        cooldown_seconds=cooldown_seconds,
    )

    # Store default LLM parameters on the adapter for consumers
    adapter.default_max_tokens = max_tokens  # type: ignore[attr-defined]
    adapter.default_temperature = temperature  # type: ignore[attr-defined]

    return adapter
