from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_CACHE_MAX_AGE = 86400  # default: 24 hours


def configure_cache_ttl(hours: int) -> None:
    """Set the pricing cache TTL from config (in hours)."""
    global _CACHE_MAX_AGE
    _CACHE_MAX_AGE = hours * 3600

_or_cache: dict[str, dict] | None = None
_or_cache_ts: float = 0.0


def _default_cache_path() -> Path:
    return Path("data/openrouter_models.json")


def _load_or_cache(cache_path: Path | None = None) -> dict[str, dict]:
    global _or_cache, _or_cache_ts
    if _or_cache is not None and (time.time() - _or_cache_ts) < _CACHE_MAX_AGE:
        return _or_cache
    cp = cache_path or _default_cache_path()
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            _or_cache = data.get("models", {})
            _or_cache_ts = data.get("fetched_at", 0)
            if (time.time() - _or_cache_ts) < _CACHE_MAX_AGE:
                return _or_cache
        except Exception as e:
            log.debug("Failed to load OpenRouter cache: %s", e)
    return _or_cache or {}


def refresh_pricing(cache_path: Path | None = None) -> dict:
    global _or_cache, _or_cache_ts
    try:
        req = urllib.request.Request(_OPENROUTER_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
        models_list = raw.get("data", [])
        models_dict: dict[str, dict] = {}
        for m in models_list:
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            models_dict[mid] = {
                "name": m.get("name", mid),
                "prompt": float(pricing.get("prompt", 0) or 0),
                "completion": float(pricing.get("completion", 0) or 0),
                "context_length": m.get("context_length", 0),
            }
        now = time.time()
        cp = cache_path or _default_cache_path()
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(
            json.dumps({"fetched_at": now, "count": len(models_dict), "models": models_dict},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _or_cache = models_dict
        _or_cache_ts = now
        log.info("OpenRouter pricing updated: %d models", len(models_dict))
        return {"count": len(models_dict), "fetched_at": now, "error": None}
    except Exception as e:
        log.warning("OpenRouter pricing fetch failed: %s", e)
        return {"count": 0, "fetched_at": 0, "error": str(e)}


_COST_PER_1M: dict[tuple[str, str], float] = {
    ("claude", "claude-opus-4-6"): 15.0,
    ("claude", "claude-sonnet-4-6"): 3.0,
    ("claude", "claude-haiku-4-5-20251001"): 0.8,
    ("deepseek", "deepseek-chat"): 0.14,
    ("deepseek", "deepseek-coder"): 0.14,
    ("ollama", ""): 0.0,
    ("lmstudio", ""): 0.0,
}

_PROVIDER_FALLBACK: dict[str, float] = {
    "claude": 3.0,
    "deepseek": 0.14,
    "ollama": 0.0,
    "lmstudio": 0.0,
}


def _find_or_price(provider: str, model: str) -> tuple[float, float] | None:
    cache = _load_or_cache()
    if not cache:
        return None
    mappings = [
        f"{provider}/{model}",
        f"anthropic/{model}" if provider == "claude" else None,
    ]
    for candidate in mappings:
        if candidate and candidate in cache:
            entry = cache[candidate]
            return (entry["prompt"], entry["completion"])
    mod_lower = model.lower()
    for mid, entry in cache.items():
        if mod_lower and mod_lower in mid.lower():
            return (entry["prompt"], entry["completion"])
    return None


def estimate_cost(
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    prov = provider.lower()
    if prov in ("ollama", "lmstudio"):
        return 0.0
    total = input_tokens + output_tokens
    if total <= 0:
        return 0.0

    or_price = _find_or_price(prov, model)
    if or_price is not None:
        prompt_rate, completion_rate = or_price
        billable_input = input_tokens - cached_tokens
        return round(
            max(0, billable_input) * prompt_rate
            + cached_tokens * prompt_rate * 0.1
            + output_tokens * completion_rate,
            8,
        )

    price = _COST_PER_1M.get((prov, model))
    if price is None:
        for (p, m), v in _COST_PER_1M.items():
            if p == prov and m and m in model:
                price = v
                break
    if price is None:
        price = _PROVIDER_FALLBACK.get(prov, 0.0)
    return round(price * total / 1_000_000, 8)
