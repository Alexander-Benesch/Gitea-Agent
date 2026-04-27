from __future__ import annotations

import pytest

from samuel.core.errors import AgentAbort, GateFailed, ProviderUnavailable, SecurityViolation


def test_agent_abort():
    with pytest.raises(AgentAbort):
        raise AgentAbort("stopped")


def test_agent_abort_fields():
    exc = AgentAbort("halt", gate=5, issue=42)
    assert exc.gate == 5
    assert exc.issue == 42
    assert "halt" in str(exc)


def test_agent_abort_defaults():
    exc = AgentAbort("simple")
    assert exc.gate is None
    assert exc.issue is None


def test_security_violation():
    with pytest.raises(SecurityViolation):
        raise SecurityViolation("forbidden")


def test_gate_failed_fields():
    exc = GateFailed(gate=3, reason="lint failed", owasp_risk="A06")
    assert exc.gate == 3
    assert exc.reason == "lint failed"
    assert exc.owasp_risk == "A06"
    assert "Gate 3 failed" in str(exc)


def test_gate_failed_string_gate():
    exc = GateFailed(gate="external:sonar", reason="quality")
    assert exc.gate == "external:sonar"
    assert exc.owasp_risk is None


def test_provider_unavailable_fields():
    exc = ProviderUnavailable(provider="anthropic", reason="rate limit")
    assert exc.provider == "anthropic"
    assert exc.reason == "rate limit"
    assert "anthropic" in str(exc)
