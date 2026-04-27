from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus, MetricsMiddleware
from samuel.core.commands import HealthCheckCommand
from samuel.core.ports import IConfig, IVersionControl
from samuel.core.types import Comment, Issue
from samuel.slices.dashboard.handler import DashboardHandler


class MockSCM(IVersionControl):
    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="T", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class MockConfig(IConfig):
    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        pass


class TestDashboardHandler:
    def test_status_with_scm(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig({"agent.mode": "watch"}))
        status = handler.get_status()
        assert status["scm_connected"] is True
        assert status["mode"] == "watch"

    def test_status_without_scm(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=None, config=MockConfig())
        status = handler.get_status()
        assert status["scm_connected"] is False

    def test_health_all_connected(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        health = handler.get_health()
        assert health["healthy"] is True

    def test_health_scm_missing(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=None, config=MockConfig())
        health = handler.get_health()
        assert health["healthy"] is False
        assert health["checks"]["scm"] is False

    def test_metrics_from_middleware(self):
        bus = Bus()
        mw = MetricsMiddleware()
        bus.add_middleware(mw)
        mw.counts["PlanIssue"] = 5
        mw.errors["PlanIssue"] = 1

        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        metrics = handler.get_metrics()
        assert metrics["counts"]["PlanIssue"] == 5
        assert metrics["errors"]["PlanIssue"] == 1

    def test_metrics_empty_without_middleware(self):
        bus = Bus()
        handler = DashboardHandler(bus)
        metrics = handler.get_metrics()
        assert metrics["counts"] == {}

    def test_api_data_endpoints(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        assert "scm_connected" in handler.get_api_data("status")
        assert "healthy" in handler.get_api_data("health")
        assert "counts" in handler.get_api_data("metrics")
        assert "error" in handler.get_api_data("unknown")


class TestSetFeatureFlag:
    def test_toggle_known_flag_updates_override(self):
        import tempfile

        from samuel.core.config import FileConfig
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FileConfig(tmp)
            bus = Bus()
            handler = DashboardHandler(bus, config=cfg)

            result = handler.set_feature_flag("eval", False)

            assert result["updated"] is True
            assert result["enabled"] is False
            assert cfg.feature_flag("eval") is False

            result2 = handler.set_feature_flag("eval", True)
            assert result2["updated"] is True
            assert cfg.feature_flag("eval") is True

    def test_toggle_unknown_flag_rejected(self):
        import tempfile

        from samuel.core.config import FileConfig
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FileConfig(tmp)
            bus = Bus()
            handler = DashboardHandler(bus, config=cfg)

            result = handler.set_feature_flag("not_a_real_flag", True)

            assert result["updated"] is False
            assert "unknown flag" in result["error"]

    def test_toggle_without_config_returns_error(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=None)

        result = handler.set_feature_flag("eval", True)
        assert result["updated"] is False

    def test_toggle_with_config_without_overrides_returns_error(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())

        result = handler.set_feature_flag("eval", True)
        assert result["updated"] is False
        assert "does not support overrides" in result["error"]


class TestSelfCheck:
    def test_self_check_returns_structured_checks(self):
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {
                "healthy": True,
                "checks": {
                    "python": {"passed": True, "version": "3.12.0"},
                    "scm": {"passed": False, "error": "boom"},
                },
            },
        )
        handler = DashboardHandler(bus, config=MockConfig({"agent.mode": "watch"}))

        result = handler.get_self_check()

        assert result["healthy"] is True
        assert result["mode"] == "watch"
        names = {c["name"] for c in result["checks"]}
        assert names == {"python", "scm"}
        python_check = next(c for c in result["checks"] if c["name"] == "python")
        assert python_check["status"] == "OK"
        assert "version=3.12.0" in python_check["detail"]
        scm_check = next(c for c in result["checks"] if c["name"] == "scm")
        assert scm_check["status"] == "FAIL"
        assert "error=boom" in scm_check["detail"]

    def test_self_check_mode_self(self):
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.self_mode": True, "agent.mode": "standard"})
        )
        result = handler.get_self_check()
        assert result["mode"] == "self"

    def test_self_check_with_no_handler_is_safe(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        result = handler.get_self_check()
        assert result["healthy"] is False
        assert result["checks"] == []

    def test_self_check_sends_health_check_command(self):
        bus = Bus()
        captured: list = []

        def _h(cmd):
            captured.append(cmd)
            return {"healthy": True, "checks": {}}

        bus.register_command("HealthCheck", _h)
        handler = DashboardHandler(bus, config=MockConfig())

        handler.get_self_check()

        assert len(captured) == 1
        assert isinstance(captured[0], HealthCheckCommand)


class TestLLMRouting:
    def test_routing_included_in_get_llm(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig({"llm.default.provider": "ollama", "llm.default.model": "llama3"}))
        data = handler.get_llm()
        assert "routing" in data
        assert isinstance(data["routing"], list)
        assert data["routing"][0]["provider"] == "ollama"


class TestTamperEvents:
    def test_security_includes_tamper_events_key(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        sec = handler.get_security()
        assert "tamper_events" in sec
        assert isinstance(sec["tamper_events"], list)
