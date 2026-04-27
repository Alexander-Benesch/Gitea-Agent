from __future__ import annotations

import logging

from samuel.core.ports import IConfig, ILLMProvider
from samuel.premium.llm_routing.router import RoutingLLMProvider

log = logging.getLogger(__name__)


def create_routing_provider(
    providers: dict[str, ILLMProvider],
    config: IConfig | None = None,
) -> RoutingLLMProvider:
    default = "ollama"
    if config:
        default = str(config.get("llm.routing.default_provider", "ollama"))
    return RoutingLLMProvider(providers, config=config, default_provider=default)
