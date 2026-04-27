from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from samuel.core.ports import INotificationSink

log = logging.getLogger(__name__)


class SlackNotifier(INotificationSink):
    def __init__(self, webhook_url: str, channel: str = "") -> None:
        self._url = webhook_url
        self._channel = channel

    def notify(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) if hasattr(event, "payload") else {}
        event_name = getattr(event, "name", str(type(event).__name__))

        is_error = "Failed" in event_name or "Blocked" in event_name
        color = "#dc3545" if is_error else "#28a745"

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{event_name}*"},
            },
        ]

        if payload:
            fields = []
            for k, v in list(payload.items())[:6]:
                fields.append({"type": "mrkdwn", "text": f"*{k}:* {v}"})
            if fields:
                blocks.append({"type": "section", "fields": fields})

        body: dict[str, Any] = {
            "blocks": blocks,
            "attachments": [{"color": color, "text": ""}],
        }
        if self._channel:
            body["channel"] = self._channel

        self._send(body)

    def _send(self, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as exc:
            log.warning("Slack notification failed: %s", exc)
