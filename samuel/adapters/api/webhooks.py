from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import PlanIssueCommand, ScanIssuesCommand
from samuel.core.events import IssueReady

log = logging.getLogger(__name__)


class WebhookIngressAdapter:
    def __init__(self, bus: Bus, secret: str = "") -> None:
        self._bus = bus
        self._secret = secret

    def handle_webhook(self, event_type: str, payload: dict[str, Any], signature: str = "") -> dict[str, Any]:
        if self._secret and not self._verify_signature(payload, signature):
            return {"status": 401, "error": "invalid signature"}

        if event_type == "issue-created":
            return self._on_issue_created(payload)

        if event_type == "issue-labeled":
            return self._on_issue_labeled(payload)

        if event_type == "push":
            return self._on_push(payload)

        return {"status": 200, "action": "ignored", "event_type": event_type}

    def _on_issue_created(self, payload: dict[str, Any]) -> dict[str, Any]:
        issue_number = payload.get("issue", {}).get("number", 0)
        if not issue_number:
            return {"status": 400, "error": "missing issue number"}

        self._bus.publish(IssueReady(
            payload={"issue": issue_number, "source": "webhook"},
        ))
        return {"status": 202, "action": "issue_ready", "issue": issue_number}

    def _on_issue_labeled(self, payload: dict[str, Any]) -> dict[str, Any]:
        issue_number = payload.get("issue", {}).get("number", 0)
        label = payload.get("label", {}).get("name", "")

        if label == "status:approved" and issue_number:
            self._bus.send(PlanIssueCommand(issue_number=issue_number))
            return {"status": 202, "action": "plan_dispatched", "issue": issue_number}

        return {"status": 200, "action": "ignored"}

    def _on_push(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._bus.send(ScanIssuesCommand())
        return {"status": 202, "action": "scan_triggered"}

    def _verify_signature(self, payload: dict[str, Any], signature: str) -> bool:
        if not signature:
            return False
        import json
        body = json.dumps(payload, separators=(",", ":")).encode()
        expected = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
