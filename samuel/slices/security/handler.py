from __future__ import annotations

import logging
import re
from typing import Any

from samuel.core.bus import Bus
from samuel.core.ports import IConfig

log = logging.getLogger(__name__)

SENSITIVE_PATTERNS = [
    r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}",
    r"(?i)bearer\s+[a-zA-Z0-9\-_\.]{20,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"sk-[a-zA-Z0-9]{32,}",
]

BLOCKED_COMMANDS = {"DROP", "DELETE FROM", "TRUNCATE", "rm -rf", "force-push"}


class SecurityHandler:
    def __init__(
        self,
        bus: Bus,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config

    def scan_for_secrets(self, content: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for i, line in enumerate(content.splitlines(), 1):
            for pattern in SENSITIVE_PATTERNS:
                if re.search(pattern, line):
                    findings.append({
                        "line": i,
                        "pattern": pattern.split(")")[0] + ")" if ")" in pattern else pattern[:30],
                        "severity": "high",
                    })
                    break
        return findings

    def check_prompt_injection(self, text: str) -> dict[str, Any]:
        indicators: list[str] = []
        lower = text.lower()

        injection_phrases = [
            "ignore previous instructions",
            "ignore all instructions",
            "ignore your instructions",
            "disregard your",
            "you are now",
            "new instructions:",
            "system prompt:",
        ]

        for phrase in injection_phrases:
            if phrase in lower:
                indicators.append(phrase)

        return {
            "suspicious": len(indicators) > 0,
            "indicators": indicators,
        }

    def validate_command_safety(self, command_text: str) -> dict[str, Any]:
        blocked: list[str] = []
        upper = command_text.upper()
        for cmd in BLOCKED_COMMANDS:
            if cmd.upper() in upper:
                blocked.append(cmd)
        return {
            "safe": len(blocked) == 0,
            "blocked_patterns": blocked,
        }
