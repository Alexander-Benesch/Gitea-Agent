from __future__ import annotations

import hmac
import logging

log = logging.getLogger(__name__)


class APIKeyAuth:
    def __init__(self, valid_keys: list[str] | None = None) -> None:
        self._valid_keys = set(valid_keys or [])

    def authenticate(self, headers: dict[str, str]) -> bool:
        if not self._valid_keys:
            return True

        # Case-insensitive header lookup (HTTP headers are case-insensitive
        # and different clients / proxies normalise casing differently).
        lc = {k.lower(): v for k, v in headers.items()}

        auth = lc.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            return any(hmac.compare_digest(token, k) for k in self._valid_keys)

        api_key = lc.get("x-api-key", "")
        if api_key:
            return any(hmac.compare_digest(api_key, k) for k in self._valid_keys)

        return False
