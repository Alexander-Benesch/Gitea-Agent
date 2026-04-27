"""Integration tests for the Phase 14.6 dashboard server wiring.

Covers:
- HTML + /api/* routes require API key when SAMUEL_API_KEY is set
- No auth in dev-mode (SAMUEL_API_KEY not set)
- /api/v1/dashboard/self_check returns checks list
- /api/v1/setup/labels reachable via RestAPI (delegates to SetupHandler)
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import HTTPServer

import pytest

from samuel.core.bus import Bus
from samuel.server import create_server


@contextmanager
def _serve(srv: HTTPServer):
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _url(srv: HTTPServer, path: str) -> str:
    host, port = srv.server_address
    # host may be bytes/0.0.0.0 — normalise
    host_str = "127.0.0.1" if str(host) in ("0.0.0.0", "", "b''") else str(host)
    return f"http://{host_str}:{port}{path}"


class TestServerAuthEnabled:
    def test_dashboard_html_requires_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "secret-xyz")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            # Without key: 401
            req = urllib.request.Request(_url(srv, "/"))
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            assert exc_info.value.code == 401

            # With key (X-API-Key, urllib normalises casing — must still work): 200 HTML
            req2 = urllib.request.Request(_url(srv, "/"), headers={"X-API-Key": "secret-xyz"})
            resp = urllib.request.urlopen(req2, timeout=2)
            assert resp.status == 200
            assert b"S.A.M.U.E.L." in resp.read()

    def test_api_dashboard_endpoints_require_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "abc-123")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            req = urllib.request.Request(_url(srv, "/api/v1/dashboard/status"))
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            assert exc_info.value.code == 401

            req2 = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/status"),
                headers={"Authorization": "Bearer abc-123"},
            )
            resp = urllib.request.urlopen(req2, timeout=2)
            assert resp.status == 200


class TestServerDevMode:
    def test_no_auth_required_when_key_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            resp = urllib.request.urlopen(_url(srv, "/"), timeout=2)
            assert resp.status == 200
            resp2 = urllib.request.urlopen(_url(srv, "/api/v1/dashboard/status"), timeout=2)
            assert resp2.status == 200


class TestSelfCheckRoute:
    def test_self_check_endpoint_returns_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {"healthy": True, "checks": {"python": {"passed": True, "version": "3.12"}}},
        )
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            import json as _json
            resp = urllib.request.urlopen(_url(srv, "/api/v1/dashboard/self_check"), timeout=2)
            body = _json.loads(resp.read())
            assert body["healthy"] is True
            assert any(c["name"] == "python" for c in body["checks"])


class TestSettingsFlagRoute:
    def test_settings_flag_updates_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        from samuel.core.config import FileConfig

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        cfg = FileConfig(tmp_path)
        srv = create_server(bus, host="127.0.0.1", port=0, config=cfg)
        with _serve(srv):
            import json as _json
            data = _json.dumps({"name": "eval", "enabled": False}).encode()
            req = urllib.request.Request(
                _url(srv, "/api/v1/settings/flag"),
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            body = _json.loads(resp.read())
            assert body.get("updated") is True
            assert cfg.feature_flag("eval") is False


class TestSetupLabelsRoute:
    def test_setup_labels_route_reachable(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        class _FakeSCM:
            def list_labels(self):
                return []

            def create_label(self, name, color, description=""):
                return {"id": 1, "name": name, "color": color, "description": description}

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})

        # Stage labels.json inside tmp_path/config, and chdir into tmp_path so
        # SetupHandler (project_root=.) picks it up.
        (tmp_path / "config").mkdir()
        import json as _json
        (tmp_path / "config" / "labels.json").write_text(
            _json.dumps({"labels": [{"name": "ready-for-agent", "color": "0e8a16"}]})
        )
        monkeypatch.chdir(tmp_path)

        srv = create_server(bus, host="127.0.0.1", port=0, scm=_FakeSCM())
        with _serve(srv):
            req = urllib.request.Request(
                _url(srv, "/api/v1/setup/labels"),
                data=b"",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            body = _json.loads(resp.read())
            assert body.get("synced") is True
            assert "ready-for-agent" in body.get("created", [])
