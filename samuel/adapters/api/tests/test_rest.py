"""Tests for REST API, webhook ingress, and API key auth."""
from __future__ import annotations

import hashlib
import hmac
import json

from samuel.adapters.api.auth import APIKeyAuth
from samuel.adapters.api.rest import RestAPI
from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.core.bus import Bus
from samuel.core.events import IssueReady

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


def _make_bus_with_handlers() -> Bus:
    """Create a Bus with dummy command handlers so send() doesn't warn."""
    bus = Bus()
    bus.register_command("PlanIssue", lambda cmd: {"ok": True, "issue": cmd.issue_number})
    bus.register_command("Implement", lambda cmd: {"ok": True, "issue": cmd.issue_number})
    bus.register_command("HealthCheck", lambda cmd: {"status": "healthy"})
    bus.register_command("ScanIssues", lambda cmd: {"scanned": True})
    return bus


# ---------------------------------------------------------------------------
# Tests: RestAPI
# ---------------------------------------------------------------------------


class TestRestAPI:
    """Tests for RestAPI request routing."""

    def test_post_plan_dispatches_plan_issue_command(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/42/plan")

        assert resp["status"] == 202
        assert resp["data"]["ok"] is True
        assert resp["data"]["issue"] == 42

    def test_post_implement_dispatches_implement_command(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/7/implement")

        assert resp["status"] == 202
        assert resp["data"]["ok"] is True
        assert resp["data"]["issue"] == 7

    def test_get_health_returns_200(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("GET", "/api/v1/health")

        assert resp["status"] == 200
        assert resp["data"]["status"] == "healthy"

    def test_get_metrics_returns_data(self):
        from samuel.core.bus import MetricsMiddleware

        bus = _make_bus_with_handlers()
        mw = MetricsMiddleware()
        bus.add_middleware(mw)
        api = RestAPI(bus)

        resp = api.handle_request("GET", "/api/metrics")

        assert resp["status"] == 200
        assert "counts" in resp["data"]
        assert "errors" in resp["data"]

    def test_unknown_route_returns_404(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("GET", "/api/v1/nonexistent")

        assert resp["status"] == 404
        assert "not found" in resp["error"]

    def test_auth_failure_returns_401(self):
        bus = _make_bus_with_handlers()
        auth = APIKeyAuth(valid_keys=["secret123"])
        api = RestAPI(bus, auth_middleware=auth)

        resp = api.handle_request("GET", "/api/v1/health", headers={"Authorization": "Bearer wrong"})

        assert resp["status"] == 401
        assert resp["error"] == "unauthorized"

    def test_auth_success_allows_request(self):
        bus = _make_bus_with_handlers()
        auth = APIKeyAuth(valid_keys=["secret123"])
        api = RestAPI(bus, auth_middleware=auth)

        resp = api.handle_request(
            "GET",
            "/api/v1/health",
            headers={"Authorization": "Bearer secret123"},
        )

        assert resp["status"] == 200


# ---------------------------------------------------------------------------
# Tests: WebhookIngressAdapter
# ---------------------------------------------------------------------------


class TestWebhookIngressAdapter:
    """Tests for the webhook ingress adapter."""

    def test_issue_created_publishes_issue_ready(self):
        bus = _make_bus_with_handlers()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)

        payload = {"issue": {"number": 5}}
        resp = wh.handle_webhook("issue-created", payload)

        assert resp["status"] == 202
        assert resp["action"] == "issue_ready"
        issue_ready_events = [e for e in events if isinstance(e, IssueReady)]
        assert len(issue_ready_events) == 1
        assert issue_ready_events[0].payload["issue"] == 5

    def test_issue_labeled_with_approved_dispatches_plan(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        payload = {"issue": {"number": 10}, "label": {"name": "status:approved"}}
        resp = wh.handle_webhook("issue-labeled", payload)

        assert resp["status"] == 202
        assert resp["action"] == "plan_dispatched"
        assert resp["issue"] == 10

    def test_push_triggers_scan(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook("push", {"ref": "refs/heads/main"})

        assert resp["status"] == 202
        assert resp["action"] == "scan_triggered"

    def test_unknown_event_type_ignored(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook("unknown-event", {})

        assert resp["status"] == 200
        assert resp["action"] == "ignored"

    def test_invalid_signature_returns_401(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")

        resp = wh.handle_webhook("issue-created", {"issue": {"number": 1}}, signature="bad-sig")

        assert resp["status"] == 401
        assert "invalid signature" in resp["error"]

    def test_valid_signature_accepted(self):
        secret = "my-secret"
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret=secret)

        payload = {"issue": {"number": 3}}
        body = json.dumps(payload, separators=(",", ":")).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        resp = wh.handle_webhook("issue-created", payload, signature=sig)

        assert resp["status"] == 202

    def test_missing_issue_number_returns_400(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook("issue-created", {"issue": {}})

        assert resp["status"] == 400


# ---------------------------------------------------------------------------
# Tests: APIKeyAuth
# ---------------------------------------------------------------------------


class TestAPIKeyAuth:
    """Tests for the API key authentication middleware."""

    def test_no_keys_allows_all(self):
        auth = APIKeyAuth(valid_keys=None)

        assert auth.authenticate({}) is True
        assert auth.authenticate({"Authorization": "Bearer anything"}) is True

    def test_empty_keys_allows_all(self):
        auth = APIKeyAuth(valid_keys=[])

        assert auth.authenticate({}) is True

    def test_valid_bearer_token_passes(self):
        auth = APIKeyAuth(valid_keys=["token-abc"])

        assert auth.authenticate({"Authorization": "Bearer token-abc"}) is True

    def test_valid_x_api_key_passes(self):
        auth = APIKeyAuth(valid_keys=["key-xyz"])

        assert auth.authenticate({"X-API-Key": "key-xyz"}) is True

    def test_invalid_token_rejects(self):
        auth = APIKeyAuth(valid_keys=["correct-key"])

        assert auth.authenticate({"Authorization": "Bearer wrong-key"}) is False

    def test_no_auth_header_rejects(self):
        auth = APIKeyAuth(valid_keys=["some-key"])

        assert auth.authenticate({}) is False

    def test_lowercase_header_works(self):
        auth = APIKeyAuth(valid_keys=["key-123"])

        assert auth.authenticate({"authorization": "Bearer key-123"}) is True
        assert auth.authenticate({"x-api-key": "key-123"}) is True


# ---------------------------------------------------------------------------
# Tests: Phase 14.6 endpoints (POST /setup/labels, POST /settings/flag)
# ---------------------------------------------------------------------------


class _StubSetup:
    def __init__(self, result: dict):
        self._result = result
        self.called = False

    def sync_labels(self) -> dict:
        self.called = True
        return self._result


class _StubDashboard:
    def __init__(self, result: dict):
        self._result = result
        self.calls: list[tuple[str, bool]] = []

    def set_feature_flag(self, name: str, enabled: bool) -> dict:
        self.calls.append((name, enabled))
        return self._result


class TestRestAPISetupLabels:
    def test_post_setup_labels_invokes_handler(self):
        bus = _make_bus_with_handlers()
        setup = _StubSetup({"synced": True, "created": ["a"], "skipped": [], "errors": []})
        api = RestAPI(bus, setup_handler=setup)

        resp = api.handle_request("POST", "/api/v1/setup/labels")

        assert resp["status"] == 200
        assert setup.called is True
        assert resp["data"]["created"] == ["a"]

    def test_post_setup_labels_without_handler_returns_503(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/setup/labels")

        assert resp["status"] == 503


class TestRestAPISettingsFlag:
    def test_post_settings_flag_updates(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": True, "name": "eval", "enabled": True})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST", "/api/v1/settings/flag", body={"name": "eval", "enabled": True}
        )

        assert resp["status"] == 200
        assert dash.calls == [("eval", True)]
        assert resp["data"]["enabled"] is True

    def test_post_settings_flag_missing_body_returns_400(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": False, "error": "x"})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request("POST", "/api/v1/settings/flag", body={})
        assert resp["status"] == 400

    def test_post_settings_flag_unknown_returns_400(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": False, "error": "unknown flag: foo"})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST", "/api/v1/settings/flag", body={"name": "foo", "enabled": True}
        )
        assert resp["status"] == 400

    def test_post_settings_flag_without_handler_returns_503(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request(
            "POST", "/api/v1/settings/flag", body={"name": "eval", "enabled": True}
        )
        assert resp["status"] == 503
