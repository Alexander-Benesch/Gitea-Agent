from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from samuel.core.ports import IAuthProvider

log = logging.getLogger(__name__)

_TRANSIENT_HTTP_CODES = (502, 503, 504)
_MAX_RETRIES = 2


class GitHubAPIError(Exception):
    def __init__(self, status: int, method: str, path: str, body: str = ""):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"GitHub API {method} {path} → {status}: {body[:200]}")


class GitHubAPI:
    def __init__(self, auth: IAuthProvider, *, base_url: str = "https://api.github.com"):
        self._base_url = base_url.rstrip("/")
        self._auth = auth

    def request(
        self, method: str, path: str, data: dict | None = None
    ) -> dict | list | None:
        url = f"{self._base_url}{path}"
        payload = json.dumps(data).encode() if data else None
        headers = {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        log.debug("%s %s", method, path)
        for attempt in range(_MAX_RETRIES + 1):
            req = urllib.request.Request(
                url, data=payload, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    body = resp.read()
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as e:
                if e.code in _TRANSIENT_HTTP_CODES and attempt < _MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                err_body = e.read().decode()[:200] if hasattr(e, "read") else ""
                raise GitHubAPIError(e.code, method, path, err_body) from e
            except (urllib.error.URLError, TimeoutError):
                if attempt < _MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                raise
