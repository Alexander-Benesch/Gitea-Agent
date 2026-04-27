from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from samuel.core.ports import IAuthProvider

log = logging.getLogger(__name__)

TOKEN_TTL_SECONDS = 3600
REFRESH_MARGIN_SECONDS = 300


class GitHubTokenAuth(IAuthProvider):
    def __init__(self, token: str) -> None:
        self._token = token

    def get_token(self) -> str:
        return self._token

    def is_valid(self) -> bool:
        return bool(self._token)

    def refresh(self) -> None:
        pass


class GitHubAppAuth(IAuthProvider):
    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: str,
        *,
        base_url: str = "https://api.github.com",
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._base_url = base_url.rstrip("/")
        self._token: str = ""
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if time.time() >= self._expires_at - REFRESH_MARGIN_SECONDS:
            self.refresh()
        return self._token

    def is_valid(self) -> bool:
        return bool(self._token) and time.time() < self._expires_at

    def refresh(self) -> None:
        jwt = self._create_jwt()
        url = f"{self._base_url}/app/installations/{self._installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/vnd.github+json",
        }
        req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
            self._token = data["token"]
            self._expires_at = time.time() + TOKEN_TTL_SECONDS
            log.info("GitHub App token refreshed (installation %s)", self._installation_id)
        except (urllib.error.HTTPError, KeyError) as e:
            log.error("Failed to refresh GitHub App token: %s", e)
            raise

    def _create_jwt(self) -> str:
        import base64

        now = int(time.time())
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"iat": now - 60, "exp": now + 600, "iss": self._app_id}).encode()
        ).rstrip(b"=")
        signing_input = header + b"." + payload
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key = serialization.load_pem_private_key(
                self._private_key.encode(), password=None
            )
            signature = base64.urlsafe_b64encode(
                private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
            ).rstrip(b"=")
        except ImportError as exc:
            raise RuntimeError(
                "GitHubAppAuth requires the 'cryptography' package for RS256 JWT signing. "
                "Install with: pip install 'samuel[github]'"
            ) from exc
        return (signing_input + b"." + signature).decode()
