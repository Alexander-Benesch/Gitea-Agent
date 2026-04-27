from __future__ import annotations

from collections.abc import Callable

Upcaster = Callable[[dict], dict]

UPCASTERS: dict[tuple[str, int], Upcaster] = {
    ("GateFailed", 1): lambda e: {**e, "owasp_risk": "unknown", "event_version": 2},
    ("LLMCallCompleted", 1): lambda e: {**e, "latency_ms": 0, "event_version": 2},
}


def upcast(event: dict) -> dict:
    key = (event.get("event_name", event.get("name", "")), event.get("event_version", 1))
    while key in UPCASTERS:
        event = UPCASTERS[key](event)
        key = (event.get("event_name", event.get("name", "")), event.get("event_version"))
    return event
