from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

_USER_AGENT = "S.A.M.U.E.L./2.0"
_TRANSIENT_HTTP_CODES = (502, 503, 504)
_MAX_RETRIES = 2
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


class HttpClientConfig:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        network = cfg.get("network", {})
        scm = cfg.get("scm", {})
        self.tls_verify: bool = scm.get("tls_verify", True)
        self.ca_bundle: str | None = scm.get("ca_bundle")
        self.max_retries: int = scm.get("max_retries", 2)
        self.transient_codes: tuple[int, ...] = tuple(
            scm.get("transient_codes", [502, 503, 504])
        )
        self.http_proxy: str = network.get("http_proxy", "") or os.environ.get("HTTP_PROXY", "")
        self.https_proxy: str = network.get("https_proxy", "") or os.environ.get("HTTPS_PROXY", "")
        self.timeout: int = network.get("timeout", 60)
        self._opener: urllib.request.OpenerDirector | None = None

    def build_ssl_context(self) -> ssl.SSLContext | None:
        if not self.tls_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            log.warning("TLS verification DISABLED — not recommended for production")
            return ctx
        if self.ca_bundle:
            ctx = ssl.create_default_context(cafile=self.ca_bundle)
            return ctx
        return None

    def build_opener(self) -> urllib.request.OpenerDirector:
        if self._opener is not None:
            return self._opener

        handlers: list[urllib.request.BaseHandler] = []

        ssl_ctx = self.build_ssl_context()
        if ssl_ctx:
            handlers.append(urllib.request.HTTPSHandler(context=ssl_ctx))

        if self.https_proxy or self.http_proxy:
            proxies: dict[str, str] = {}
            if self.http_proxy:
                proxies["http"] = self.http_proxy
            if self.https_proxy:
                proxies["https"] = self.https_proxy
            handlers.append(urllib.request.ProxyHandler(proxies))
            log.info("HTTP proxy configured: %s", proxies)

        self._opener = urllib.request.build_opener(*handlers)
        return self._opener


def http_request(
    method: str,
    url: str,
    data: dict | None = None,
    headers: dict[str, str] | None = None,
    *,
    config: HttpClientConfig | None = None,
    retries: int | None = None,
    timeout: int | None = None,
) -> dict | list | None:
    cfg = config or HttpClientConfig()
    effective_retries = retries if retries is not None else cfg.max_retries
    opener = cfg.build_opener()
    actual_timeout = timeout or cfg.timeout

    req_headers = {
        "User-Agent": _USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)

    payload = json.dumps(data).encode() if data else None

    for attempt in range(effective_retries + 1):
        req = urllib.request.Request(
            url, data=payload, headers=req_headers, method=method
        )
        try:
            with opener.open(req, timeout=actual_timeout) as resp:
                body = resp.read(_MAX_RESPONSE_BYTES)
                return json.loads(body) if body else None
        except urllib.error.HTTPError as e:
            if e.code in cfg.transient_codes and attempt < effective_retries:
                time.sleep(2**attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < effective_retries:
                time.sleep(2**attempt)
                continue
            raise
