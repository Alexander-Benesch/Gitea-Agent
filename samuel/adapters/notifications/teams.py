from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from samuel.core.ports import INotificationSink

log = logging.getLogger(__name__)


class TeamsNotifier(INotificationSink):
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def notify(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) if hasattr(event, "payload") else {}
        event_name = getattr(event, "name", str(type(event).__name__))

        is_error = "Failed" in event_name or "Blocked" in event_name
        color = "attention" if is_error else "good"

        facts = [{"title": k, "value": str(v)} for k, v in list(payload.items())[:6]]

        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": event_name,
                            "weight": "bolder",
                            "size": "medium",
                            "color": color,
                        },
                        {
                            "type": "FactSet",
                            "facts": facts,
                        },
                    ],
                },
            }],
        }

        self._send(card)

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
            log.warning("Teams notification failed: %s", exc)
