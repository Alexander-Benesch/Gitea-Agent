from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import EvaluateCommand
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.types import Comment, Issue
from samuel.slices.evaluation.handler import EvaluationHandler


class MockSCM(IVersionControl):
    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
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


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


def _eval_config_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "eval.json").write_text(
        '{"weights": {"test_pass_rate": 0.3, "syntax_valid": 0.2, '
        '"hallucination_free": 0.3, "scope_compliant": 0.2}, '
        '"baseline": 0.8, "fail_fast_on": ["syntax_valid"]}'
    )
    return cfg


ALL_PASS = {
    "test_pass_rate": 1.0,
    "syntax_valid": 1.0,
    "hallucination_free": 1.0,
    "scope_compliant": 1.0,
}


class TestEvaluationHandler:
    def test_eval_pass(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)
        scm = MockSCM()

        handler = EvaluationHandler(bus, scm=scm, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        assert result["passed"] is True
        assert result["score"] == 1.0
        assert any(e.name == "EvalCompleted" for e in events)
        assert not any(e.name == "EvalFailed" for e in events)
        assert len(scm.posted) == 1
        assert "PASS" in scm.posted[0][1]

    def test_eval_fail_low_score(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": {
                "test_pass_rate": 0.3,
                "syntax_valid": 0.9,
                "hallucination_free": 0.3,
                "scope_compliant": 0.3,
            }},
        ))

        assert result["passed"] is False
        assert any(e.name == "EvalFailed" for e in events)

    def test_fail_fast_blocks_despite_high_total(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": {
                "test_pass_rate": 1.0,
                "syntax_valid": 0.5,
                "hallucination_free": 1.0,
                "scope_compliant": 1.0,
            }},
        ))

        assert result["passed"] is False
        assert "syntax_valid" in result["fail_fast_blocked"]
        assert result["score"] > 0.8
        fail_event = next(e for e in events if e.name == "EvalFailed")
        assert "syntax_valid" in fail_event.payload["fail_fast_blocked"]

    def test_no_criteria_scores_publishes_fail(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(issue_number=42))

        assert result is None
        assert any(e.name == "EvalFailed" for e in events)

    def test_score_history_written(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        import json
        history = json.loads((data / "score_history.json").read_text())
        assert len(history) == 1
        assert history[0]["issue"] == 42
        assert history[0]["score"] == 1.0

    def test_correlation_id_flows(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
            correlation_id="eval-corr-1",
        ))

        for e in events:
            assert e.correlation_id == "eval-corr-1"

    def test_no_scm_still_works(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, scm=None, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        assert result["passed"] is True
        assert any(e.name == "EvalCompleted" for e in events)

    def test_invalid_config_uses_defaults(self, tmp_path: Path):
        cfg = tmp_path / "config"
        cfg.mkdir()
        data = tmp_path / "data"
        bus = Bus()

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        assert result["passed"] is True
