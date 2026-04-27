from __future__ import annotations


class AgentAbort(Exception):
    def __init__(self, message: str, gate: int | str | None = None, issue: int | None = None):
        self.gate = gate
        self.issue = issue
        super().__init__(message)


class SecurityViolation(Exception):
    pass


class GateFailed(Exception):
    def __init__(self, gate: int | str, reason: str, owasp_risk: str | None = None):
        self.gate = gate
        self.reason = reason
        self.owasp_risk = owasp_risk
        super().__init__(f"Gate {gate} failed: {reason}")


class ProviderUnavailable(Exception):
    def __init__(self, provider: str, reason: str = ""):
        self.provider = provider
        self.reason = reason
        super().__init__(f"Provider {provider} unavailable: {reason}")
