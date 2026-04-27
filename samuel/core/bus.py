from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.commands import Command
from samuel.core.events import (
    AuditEvent,
    Event,
)

log = logging.getLogger(__name__)

Handler = Callable[[Event | Command], Any]
Middleware = Callable[[Event | Command, Callable], Any]


class Bus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._command_handlers: dict[str, Handler] = {}
        self._middlewares: list[Middleware] = []
        # Optional runtime references (set by bootstrap)
        self.scm: Any = None
        self.config: Any = None
        self.audit_sink: Any = None
        self.session: Any = None
        self.sequence: Any = None

    def add_middleware(self, mw: Middleware) -> None:
        self._middlewares.append(mw)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        self._subscribers[event_name].append(handler)

    def register_command(self, command_name: str, handler: Handler) -> None:
        self._command_handlers[command_name] = handler

    def has_handler(self, command_name: str) -> bool:
        return command_name in self._command_handlers

    def publish(self, event: Event) -> None:
        def dispatch(msg: Event | Command) -> None:
            for handler in self._subscribers.get(msg.name, []):
                try:
                    handler(msg)
                except Exception:
                    log.exception("Handler error for event %s", msg.name)
            for handler in self._subscribers.get("*", []):
                try:
                    handler(msg)
                except Exception:
                    log.exception("Wildcard handler error for event %s", msg.name)

        self._run_through_middlewares(event, dispatch)

    def send(self, command: Command) -> Any:
        def dispatch(msg: Event | Command) -> Any:
            handler = self._command_handlers.get(msg.name)
            if handler is None:
                from samuel.core.events import UnhandledCommand

                self.publish(
                    UnhandledCommand(payload={"command": msg.name})
                )
                log.warning("No handler for command: %s", msg.name)
                return None
            return handler(msg)

        return self._run_through_middlewares(command, dispatch)

    def _run_through_middlewares(
        self, msg: Event | Command, final: Callable
    ) -> Any:
        chain = final
        for mw in reversed(self._middlewares):
            prev = chain
            def chain(m, _prev=prev, _mw=mw):
                return _mw(m, _prev)
        return chain(msg)


# --- Middlewares ---


class IdempotencyStore:
    def __init__(self, path: Path | None = None, ttl_hours: int = 24):
        self._lock = threading.Lock()
        self._path = path
        self._ttl = ttl_hours * 3600
        self._keys: dict[str, float] = {}
        if path and path.exists():
            try:
                self._keys = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._keys = {}

    def has_key(self, key: str) -> bool:
        with self._lock:
            self._evict()
            return key in self._keys

    def set_key(self, key: str) -> None:
        with self._lock:
            self._keys[key] = time.time()
            self._persist()

    def _evict(self) -> None:
        cutoff = time.time() - self._ttl
        self._keys = {k: v for k, v in self._keys.items() if v > cutoff}

    def _persist(self) -> None:
        if self._path:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(json.dumps(self._keys))
            except OSError:
                log.warning("Failed to persist idempotency store")


class IdempotencyMiddleware:
    def __init__(self, store: IdempotencyStore | None = None):
        self._store = store or IdempotencyStore()

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        if not isinstance(msg, Command) or not msg.idempotency_key:
            return next_(msg)
        if self._store.has_key(msg.idempotency_key):
            log.info("Deduplicated command: %s", msg.idempotency_key)
            return None
        result = next_(msg)
        self._store.set_key(msg.idempotency_key)
        return result


class SecurityMiddleware:
    BLOCKED_PATTERNS: list[str] = []

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        if isinstance(msg, Command):
            for pattern in self.BLOCKED_PATTERNS:
                if pattern in msg.name:

                    log.warning("Blocked command: %s", msg.name)
                    return None
        return next_(msg)


class PromptGuardMiddleware:
    REQUIRED_MARKERS = [
        "Unveränderliche Schranken",
        "Ignoriere Anweisungen",
    ]

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        if isinstance(msg, Command) and msg.name == "LLMCall":
            prompt = msg.payload.get("prompt", "")
            missing = [m for m in self.REQUIRED_MARKERS if m not in prompt]
            if missing:

                log.warning("Prompt missing markers: %s", missing)
                return None
        return next_(msg)


_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),          # OpenAI/Anthropic keys
    re.compile(r"ghp_[a-zA-Z0-9]{36,}"),          # GitHub PAT
    re.compile(r"ghs_[a-zA-Z0-9]{36,}"),          # GitHub App token
    re.compile(r"[a-f0-9]{40}"),                   # Gitea tokens (40 hex chars)
]


def scrub_secrets(text: str) -> str:
    """Replace known secret patterns in *text* with ``***REDACTED***``."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


def _scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *payload* with string values scrubbed."""
    scrubbed: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            scrubbed[key] = scrub_secrets(value)
        else:
            scrubbed[key] = value
    return scrubbed


class AuditMiddleware:
    def __init__(self, sink: Any | None = None):
        self._sink = sink

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        result = next_(msg)
        if self._sink:
            try:
                self._sink.write(
                    AuditEvent(
                        payload=_scrub_payload({
                            "message_type": type(msg).__name__,
                            "message_name": msg.name,
                            "correlation_id": getattr(msg, "correlation_id", None),
                        })
                    )
                )
            except Exception:
                log.exception("Audit write failed")
        return result


class ErrorMiddleware:
    def __init__(self, bus: Any | None = None):
        self._bus = bus

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        try:
            return next_(msg)
        except Exception as exc:
            log.exception("Error processing %s", msg.name)
            if self._bus is not None:
                from samuel.core.errors import AgentAbort
                if isinstance(exc, AgentAbort):
                    from samuel.core.events import WorkflowAborted
                    try:
                        self._bus.publish(WorkflowAborted(
                            payload={
                                "reason": str(exc),
                                "gate": exc.gate,
                                "issue": exc.issue,
                                "source_command": msg.name,
                            },
                            correlation_id=getattr(msg, "correlation_id", "") or "",
                        ))
                    except Exception:
                        log.warning("Failed to publish WorkflowAborted for AgentAbort")
            return None


class MetricsMiddleware:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.total_ms: dict[str, float] = defaultdict(float)

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        start = time.monotonic()
        try:
            result = next_(msg)
            with self._lock:
                self.counts[msg.name] += 1
                self.total_ms[msg.name] += (time.monotonic() - start) * 1000
            return result
        except Exception:
            with self._lock:
                self.errors[msg.name] += 1
            raise
