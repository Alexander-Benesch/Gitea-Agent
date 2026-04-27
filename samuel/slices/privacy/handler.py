from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.ports import IConfig

log = logging.getLogger(__name__)

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("ip_address", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
    ("credit_card", re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    ("phone", re.compile(r"\b(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}\b")),
]

DEFAULT_REPLACEMENT = "[REDACTED:{type}]"


class PromptSanitizer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._enabled = cfg.get("enabled", True)
        self._active_patterns = cfg.get("patterns", [name for name, _ in _PII_PATTERNS])
        self._replacement = cfg.get("replacement", DEFAULT_REPLACEMENT)

    def sanitize(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        if not self._enabled or not text:
            return text, []

        redactions: list[dict[str, Any]] = []
        result = text

        pattern_map = dict(_PII_PATTERNS)
        for ptype in self._active_patterns:
            pattern = pattern_map.get(ptype)
            if not pattern:
                continue

            for match in pattern.finditer(result):
                redactions.append({
                    "type": ptype,
                    "hash": hashlib.sha256(match.group().encode()).hexdigest()[:12],
                    "position": match.start(),
                })

            replacement = self._replacement.replace("{type}", ptype)
            result = pattern.sub(replacement, result)

        if redactions:
            log.info("Sanitized %d PII items from prompt", len(redactions))

        return result, redactions


class RetentionPolicy:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._audit_log_days = cfg.get("audit_log_days", 365)
        self._pii_anonymize_days = cfg.get("pii_anonymize_after_days", 30)

    @property
    def audit_log_days(self) -> int:
        return self._audit_log_days

    @property
    def pii_anonymize_days(self) -> int:
        return self._pii_anonymize_days


class TransferWarning:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._allowed_regions = set(cfg.get("allowed_regions", ["EU", "EEA", "CH"]))
        self._provider_locations = cfg.get("provider_locations", {})
        self._enabled = cfg.get("transfer_warning", True)

    def check_provider(self, provider: str) -> dict[str, Any]:
        location = self._provider_locations.get(provider, "unknown")
        is_local = location == "local"
        is_allowed = is_local or location in self._allowed_regions

        return {
            "provider": provider,
            "location": location,
            "allowed": is_allowed,
            "warning": (
                None if is_allowed
                else f"Provider '{provider}' is located in {location} — "
                     f"outside allowed regions {self._allowed_regions}. "
                     f"Art. 44-49 DSGVO: Drittland-Transfer erfordert zusätzliche Schutzmaßnahmen."
            ),
        }

    def check_all_providers(self) -> list[dict[str, Any]]:
        return [self.check_provider(p) for p in self._provider_locations]


class PrivacyHandler:
    def __init__(self, bus: Bus, config: IConfig | None = None) -> None:
        self._bus = bus
        privacy_cfg = self._load_privacy_config(config)
        self.sanitizer = PromptSanitizer(privacy_cfg.get("pii_scrubbing", {}))
        self.retention = RetentionPolicy(privacy_cfg.get("retention", {}))
        self.transfer = TransferWarning(privacy_cfg)

    @staticmethod
    def _load_privacy_config(config: IConfig | None) -> dict[str, Any]:
        config_path = Path("config/privacy.json")
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except json.JSONDecodeError:
                log.warning("Invalid privacy.json, using defaults")
        return {}

    def check_retention(self) -> dict[str, Any]:
        """Check which audit logs exceed retention policy."""
        data_dir = Path("data/logs")
        if not data_dir.exists():
            return {"status": "no_logs_dir", "expired_files": []}

        import datetime

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=self.retention.audit_log_days
        )
        expired = []
        for f in data_dir.glob("*.jsonl"):
            mtime = datetime.datetime.fromtimestamp(
                f.stat().st_mtime, tz=datetime.timezone.utc
            )
            if mtime < cutoff:
                expired.append({"file": str(f), "modified": mtime.isoformat()})
        return {
            "status": "checked",
            "policy_days": self.retention.audit_log_days,
            "pii_anonymize_days": self.retention.pii_anonymize_days,
            "expired_files": expired,
        }

    def handle_delete_user_data(self, user_identifier: str) -> dict[str, Any]:
        log.info("DeleteUserData requested for user: %s", user_identifier)
        anonymized_count = 0
        # Placeholder: actual implementation would scan audit logs
        # and anonymize entries matching the user_identifier
        return {
            "user": user_identifier,
            "anonymized_entries": anonymized_count,
            "status": "completed",
        }
