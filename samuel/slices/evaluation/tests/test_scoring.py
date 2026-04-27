from __future__ import annotations

import json
from pathlib import Path

from samuel.core.config import EvalSchema
from samuel.slices.evaluation.scoring import (
    HISTORY_MAX,
    EvalResult,
    append_history,
    compute_score,
)


def _default_config(**overrides) -> EvalSchema:
    defaults = {
        "weights": {
            "test_pass_rate": 0.3,
            "syntax_valid": 0.2,
            "hallucination_free": 0.3,
            "scope_compliant": 0.2,
        },
        "baseline": 0.8,
        "fail_fast_on": ["syntax_valid"],
    }
    defaults.update(overrides)
    return EvalSchema(**defaults)


class TestComputeScore:
    def test_all_perfect(self):
        cfg = _default_config()
        result = compute_score(
            {"test_pass_rate": 1.0, "syntax_valid": 1.0, "hallucination_free": 1.0, "scope_compliant": 1.0},
            cfg,
        )
        assert result.passed is True
        assert result.score == 1.0
        assert result.fail_fast_blocked == []

    def test_all_zero(self):
        cfg = _default_config()
        result = compute_score(
            {"test_pass_rate": 0.0, "syntax_valid": 0.0, "hallucination_free": 0.0, "scope_compliant": 0.0},
            cfg,
        )
        assert result.passed is False
        assert result.score == 0.0

    def test_weighted_score_correct(self):
        cfg = _default_config()
        result = compute_score(
            {"test_pass_rate": 1.0, "syntax_valid": 1.0, "hallucination_free": 0.5, "scope_compliant": 0.5},
            cfg,
        )
        expected = 1.0 * 0.3 + 1.0 * 0.2 + 0.5 * 0.3 + 0.5 * 0.2
        assert abs(result.score - expected) < 0.001

    def test_fail_fast_blocks_despite_high_total(self):
        cfg = _default_config()
        result = compute_score(
            {"test_pass_rate": 1.0, "syntax_valid": 0.5, "hallucination_free": 1.0, "scope_compliant": 1.0},
            cfg,
        )
        assert result.passed is False
        assert "syntax_valid" in result.fail_fast_blocked
        assert result.score > 0.8

    def test_no_fail_fast_when_criterion_passes(self):
        cfg = _default_config()
        result = compute_score(
            {"test_pass_rate": 1.0, "syntax_valid": 0.9, "hallucination_free": 1.0, "scope_compliant": 1.0},
            cfg,
        )
        assert result.fail_fast_blocked == []
        assert result.passed is True

    def test_missing_criterion_scores_zero(self):
        cfg = _default_config()
        result = compute_score({"test_pass_rate": 1.0}, cfg)
        expected = 1.0 * 0.3
        assert abs(result.score - expected) < 0.001

    def test_scores_clamped_to_0_1(self):
        cfg = _default_config()
        result = compute_score(
            {"test_pass_rate": 2.0, "syntax_valid": -0.5, "hallucination_free": 1.0, "scope_compliant": 1.0},
            cfg,
        )
        tp = next(r for r in result.criteria if r.name == "test_pass_rate")
        sv = next(r for r in result.criteria if r.name == "syntax_valid")
        assert tp.score == 1.0
        assert sv.score == 0.0

    def test_empty_fail_fast_on(self):
        cfg = _default_config(fail_fast_on=[])
        result = compute_score(
            {"test_pass_rate": 0.5, "syntax_valid": 0.5, "hallucination_free": 0.5, "scope_compliant": 0.5},
            cfg,
        )
        assert result.fail_fast_blocked == []
        assert result.passed is False

    def test_just_at_baseline_passes(self):
        cfg = _default_config(fail_fast_on=[])
        result = compute_score(
            {"test_pass_rate": 0.8, "syntax_valid": 0.8, "hallucination_free": 0.8, "scope_compliant": 0.8},
            cfg,
        )
        assert result.passed is True
        assert abs(result.score - 0.8) < 0.001


class TestAppendHistory:
    def test_creates_file(self, tmp_path: Path):
        result = EvalResult(passed=True, score=0.9, baseline=0.8, criteria=[])
        history = append_history(tmp_path, 42, result)
        assert len(history) == 1
        assert history[0]["issue"] == 42
        assert history[0]["score"] == 0.9
        assert (tmp_path / "score_history.json").exists()

    def test_appends_to_existing(self, tmp_path: Path):
        (tmp_path / "score_history.json").write_text('[{"ts": "old", "issue": 1, "score": 0.5}]')
        result = EvalResult(passed=True, score=0.9, baseline=0.8, criteria=[])
        history = append_history(tmp_path, 42, result)
        assert len(history) == 2

    def test_truncates_at_max(self, tmp_path: Path):
        existing = [{"ts": f"t{i}", "issue": i, "score": 0.5} for i in range(HISTORY_MAX)]
        (tmp_path / "score_history.json").write_text(json.dumps(existing))
        result = EvalResult(passed=True, score=0.9, baseline=0.8, criteria=[])
        history = append_history(tmp_path, 999, result)
        assert len(history) == HISTORY_MAX
        assert history[-1]["issue"] == 999
        assert history[0]["issue"] == 1

    def test_handles_corrupt_json(self, tmp_path: Path):
        (tmp_path / "score_history.json").write_text("not json")
        result = EvalResult(passed=True, score=0.9, baseline=0.8, criteria=[])
        history = append_history(tmp_path, 42, result)
        assert len(history) == 1
