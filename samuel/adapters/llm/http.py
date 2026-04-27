from __future__ import annotations

import json
import urllib.request

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def http_post(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(_MAX_RESPONSE_BYTES)
        return json.loads(body)
