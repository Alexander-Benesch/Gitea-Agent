from __future__ import annotations

import logging
from typing import Any

from samuel.core.commands import create_command
from samuel.core.events import Event, UnhandledCommand

log = logging.getLogger(__name__)

_BUILTIN_CONDITIONS: dict[str, Any] = {
    "self_parity_ok": lambda event: (event.payload.get("eval_score") or 0) >= 0.6,
}


class WorkflowEngine:
    def __init__(self, bus: Any, definition: dict | None = None):
        self._bus = bus
        self._steps: list[dict] = []
        if definition:
            self.load(definition)

    def load(self, definition: dict) -> None:
        self._steps = definition.get("steps", [])
        for step in self._steps:
            event_name = step["on"]
            self._bus.subscribe(event_name, self._make_handler(step))

    def _make_handler(self, step: dict):
        def handler(event: Event) -> None:
            command_name = step["send"]
            condition = step.get("condition")
            if condition and not self._evaluate_condition(condition, event):
                log.debug("Condition not met for %s -> %s", event.name, command_name)
                return
            if not self._bus.has_handler(command_name):
                self._bus.publish(
                    UnhandledCommand(
                        payload={
                            "command": command_name,
                            "trigger": event.name,
                            "reason": f"No handler registered for '{command_name}'",
                        }
                    )
                )
                return
            cmd = create_command(
                command_name,
                payload=event.payload,
                correlation_id=event.correlation_id,
            )
            self._bus.send(cmd)

        return handler

    def _evaluate_condition(self, condition: str, event: Event) -> bool:
        if condition in _BUILTIN_CONDITIONS:
            return _BUILTIN_CONDITIONS[condition](event)
        try:
            return bool(eval(condition, {"event": event, "payload": event.payload}))  # noqa: S307
        except Exception:
            log.warning("Condition eval failed: %s", condition)
            return False
