from __future__ import annotations

import logging
from typing import Any

from samuel.core.events import Event
from samuel.core.ports import IAuditSink
from samuel.slices.audit_trail.owasp import classify

log = logging.getLogger(__name__)


class AuditHandler:
    def __init__(self, sinks: list[IAuditSink]):
        self._sinks = sinks

    def register(self, bus: Any) -> None:
        bus.subscribe("*", self.handle)

    def handle(self, event: Event) -> None:
        cat = event.payload.get("cat", "")
        evt = event.payload.get("evt", event.name)
        owasp = classify(cat, evt)

        record = {
            "event_name": event.name,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "ts": event.ts.isoformat(),
            "owasp_risk": owasp,
            "payload": event.payload,
        }

        for sink in self._sinks:
            try:
                sink.write(record)
            except Exception:
                log.exception("Audit sink write failed for %s", type(sink).__name__)
