"""Tests for notification adapters (Slack, Teams, GenericWebhook)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from samuel.adapters.notifications.generic_webhook import GenericWebhookNotifier
from samuel.adapters.notifications.slack import SlackNotifier
from samuel.adapters.notifications.teams import TeamsNotifier
from samuel.core.ports import INotificationSink

# ---------------------------------------------------------------------------
# Fake events
# ---------------------------------------------------------------------------


@dataclass
class FakeSuccessEvent:
    name: str = "PlanCreated"
    payload: dict = field(default_factory=lambda: {"issue": 42, "branch": "feat/x"})
    correlation_id: str = "corr-1"
    ts: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))


@dataclass
class FakeErrorEvent:
    name: str = "WorkflowFailed"
    payload: dict = field(default_factory=lambda: {"issue": 7, "reason": "timeout"})
    correlation_id: str = "corr-2"
    ts: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))


@dataclass
class FakeBlockedEvent:
    name: str = "WorkflowBlocked"
    payload: dict = field(default_factory=lambda: {"issue": 99})
    correlation_id: str = "corr-3"
    ts: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# Tests: SlackNotifier
# ---------------------------------------------------------------------------


class TestSlackNotifier:
    """Tests for Slack notification formatting."""

    def test_implements_interface(self):
        assert issubclass(SlackNotifier, INotificationSink)

    def test_formats_blocks_correctly(self):
        notifier = SlackNotifier("https://example.com/slack")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        assert len(sent) == 1
        body = sent[0]
        assert "blocks" in body
        assert body["blocks"][0]["text"]["text"] == "*PlanCreated*"
        # Should have a fields section for payload
        assert len(body["blocks"]) >= 2
        assert "fields" in body["blocks"][1]

    def test_success_event_gets_green_color(self):
        notifier = SlackNotifier("https://example.com/slack")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        color = sent[0]["attachments"][0]["color"]
        assert color == "#28a745"  # green / success

    def test_error_event_gets_red_color(self):
        notifier = SlackNotifier("https://example.com/slack")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeErrorEvent())

        color = sent[0]["attachments"][0]["color"]
        assert color == "#dc3545"  # red / error

    def test_blocked_event_gets_red_color(self):
        notifier = SlackNotifier("https://example.com/slack")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeBlockedEvent())

        color = sent[0]["attachments"][0]["color"]
        assert color == "#dc3545"

    def test_channel_included_when_set(self):
        notifier = SlackNotifier("https://example.com/slack", channel="#ops")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        assert sent[0]["channel"] == "#ops"

    def test_no_channel_when_empty(self):
        notifier = SlackNotifier("https://example.com/slack")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        assert "channel" not in sent[0]


# ---------------------------------------------------------------------------
# Tests: TeamsNotifier
# ---------------------------------------------------------------------------


class TestTeamsNotifier:
    """Tests for Teams adaptive card formatting."""

    def test_implements_interface(self):
        assert issubclass(TeamsNotifier, INotificationSink)

    def test_formats_adaptive_card(self):
        notifier = TeamsNotifier("https://example.com/teams")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        assert len(sent) == 1
        card = sent[0]
        assert card["type"] == "message"
        content = card["attachments"][0]["content"]
        assert content["type"] == "AdaptiveCard"
        assert content["body"][0]["text"] == "PlanCreated"

    def test_success_event_gets_good_color(self):
        notifier = TeamsNotifier("https://example.com/teams")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        color = sent[0]["attachments"][0]["content"]["body"][0]["color"]
        assert color == "good"

    def test_error_event_gets_attention_color(self):
        notifier = TeamsNotifier("https://example.com/teams")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeErrorEvent())

        color = sent[0]["attachments"][0]["content"]["body"][0]["color"]
        assert color == "attention"

    def test_facts_contain_payload_keys(self):
        notifier = TeamsNotifier("https://example.com/teams")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        facts = sent[0]["attachments"][0]["content"]["body"][1]["facts"]
        titles = [f["title"] for f in facts]
        assert "issue" in titles
        assert "branch" in titles


# ---------------------------------------------------------------------------
# Tests: GenericWebhookNotifier
# ---------------------------------------------------------------------------


class TestGenericWebhookNotifier:
    """Tests for the generic webhook notifier."""

    def test_implements_interface(self):
        assert issubclass(GenericWebhookNotifier, INotificationSink)

    def test_sends_correct_payload(self):
        notifier = GenericWebhookNotifier("https://example.com/hook")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        assert len(sent) == 1
        body = sent[0]
        assert body["event"] == "PlanCreated"
        assert body["payload"]["issue"] == 42
        assert body["correlation_id"] == "corr-1"

    def test_error_event_payload(self):
        notifier = GenericWebhookNotifier("https://example.com/hook")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeErrorEvent())

        assert sent[0]["event"] == "WorkflowFailed"
        assert sent[0]["payload"]["reason"] == "timeout"

    def test_ts_serialized(self):
        notifier = GenericWebhookNotifier("https://example.com/hook")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        notifier.notify(FakeSuccessEvent())

        # ts should be isoformat string, not empty
        assert sent[0]["ts"] != ""
        assert "2026" in sent[0]["ts"]

    def test_event_without_payload_attr(self):
        """Events without a payload attribute should still work."""
        notifier = GenericWebhookNotifier("https://example.com/hook")
        sent: list = []
        notifier._send = lambda body: sent.append(body)

        class BareEvent:
            name = "BareEvent"
            correlation_id = ""

        notifier.notify(BareEvent())

        assert sent[0]["event"] == "BareEvent"
        assert sent[0]["payload"] == {}
