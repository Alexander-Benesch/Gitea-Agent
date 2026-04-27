from __future__ import annotations

from samuel.slices.privacy.handler import (
    PromptSanitizer,
    RetentionPolicy,
    TransferWarning,
)


class TestPromptSanitizer:
    def test_scrub_email(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("Contact john@example.com for details")

        assert "john@example.com" not in text
        assert "[REDACTED:email]" in text
        assert len(redactions) == 1
        assert redactions[0]["type"] == "email"
        assert len(redactions[0]["hash"]) == 12

    def test_scrub_ip_address(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("Server at 192.168.1.100 is down")

        assert "192.168.1.100" not in text
        assert "[REDACTED:ip_address]" in text

    def test_scrub_multiple_pii(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize(
            "User test@mail.com from 10.0.0.1 called +49 170 1234567"
        )

        assert "test@mail.com" not in text
        assert "10.0.0.1" not in text
        assert len(redactions) >= 2

    def test_no_pii_returns_unchanged(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("This is a normal prompt without PII")

        assert text == "This is a normal prompt without PII"
        assert redactions == []

    def test_disabled_returns_unchanged(self):
        s = PromptSanitizer({"enabled": False})
        text, redactions = s.sanitize("Secret: john@example.com")

        assert "john@example.com" in text
        assert redactions == []

    def test_selective_patterns(self):
        s = PromptSanitizer({"patterns": ["email"]})
        text, redactions = s.sanitize("john@example.com at 192.168.1.1")

        assert "john@example.com" not in text
        assert "192.168.1.1" in text

    def test_empty_string(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("")
        assert text == ""
        assert redactions == []

    def test_credit_card(self):
        s = PromptSanitizer()
        text, redactions = s.sanitize("Card: 4111-1111-1111-1111")
        assert "4111" not in text
        assert "[REDACTED:credit_card]" in text


class TestRetentionPolicy:
    def test_defaults(self):
        r = RetentionPolicy()
        assert r.audit_log_days == 365
        assert r.pii_anonymize_days == 30

    def test_custom_values(self):
        r = RetentionPolicy({"audit_log_days": 730, "pii_anonymize_after_days": 14})
        assert r.audit_log_days == 730
        assert r.pii_anonymize_days == 14


class TestTransferWarning:
    def test_local_provider_allowed(self):
        tw = TransferWarning({
            "allowed_regions": ["EU"],
            "provider_locations": {"ollama": "local"},
        })

        result = tw.check_provider("ollama")
        assert result["allowed"] is True
        assert result["warning"] is None

    def test_eu_provider_allowed(self):
        tw = TransferWarning({
            "allowed_regions": ["EU", "EEA"],
            "provider_locations": {"mistral": "EU"},
        })

        result = tw.check_provider("mistral")
        assert result["allowed"] is True

    def test_us_provider_warning(self):
        tw = TransferWarning({
            "allowed_regions": ["EU"],
            "provider_locations": {"anthropic": "US"},
        })

        result = tw.check_provider("anthropic")
        assert result["allowed"] is False
        assert "Drittland-Transfer" in result["warning"]
        assert "Art. 44-49" in result["warning"]

    def test_cn_provider_warning(self):
        tw = TransferWarning({
            "allowed_regions": ["EU"],
            "provider_locations": {"deepseek": "CN"},
        })

        result = tw.check_provider("deepseek")
        assert result["allowed"] is False

    def test_check_all_providers(self):
        tw = TransferWarning({
            "allowed_regions": ["EU"],
            "provider_locations": {"ollama": "local", "anthropic": "US"},
        })

        results = tw.check_all_providers()
        assert len(results) == 2
        allowed = [r for r in results if r["allowed"]]
        warned = [r for r in results if not r["allowed"]]
        assert len(allowed) == 1
        assert len(warned) == 1

    def test_unknown_provider(self):
        tw = TransferWarning({
            "allowed_regions": ["EU"],
            "provider_locations": {},
        })

        result = tw.check_provider("unknown_provider")
        assert result["location"] == "unknown"
        assert result["allowed"] is False
