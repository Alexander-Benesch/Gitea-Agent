from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from samuel.core.ports import INotificationSink

log = logging.getLogger(__name__)


class GenericWebhookNotifier(INotificationSink):
    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}

    def notify(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) if hasattr(event, "payload") else {}
        event_name = getattr(event, "name", str(type(event).__name__))

        body = {
            "event": event_name,
            "payload": payload,
            "correlation_id": getattr(event, "correlation_id", ""),
            "ts": getattr(event, "ts", "").isoformat() if hasattr(getattr(event, "ts", None), "isoformat") else "",
        }

        self._send(body)

    def _send(self, body: dict[str, Any]) -> None:
        data = json.dumps(body, default=str).encode()
        headers = {"Content-Type": "application/json"}
        headers.update(self._headers)
        req = urllib.request.Request(self._url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as exc:
            log.warning("Webhook notification failed: %s", exc)
