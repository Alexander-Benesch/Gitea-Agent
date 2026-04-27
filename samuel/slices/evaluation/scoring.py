from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from samuel.core.config import EvalSchema

log = logging.getLogger(__name__)

HISTORY_MAX = 90


@dataclass
class CriterionResult:
    name: str
    score: float
    weight: float
    passed: bool
    reason: str = ""


@dataclass
class EvalResult:
    passed: bool
    score: float
    baseline: float
    criteria: list[CriterionResult] = field(default_factory=list)
    fail_fast_blocked: list[str] = field(default_factory=list)


def compute_score(
    criteria_scores: dict[str, float],
    config: EvalSchema,
) -> EvalResult:
    results: list[CriterionResult] = []
    fail_fast_blocked: list[str] = []

    for name, weight in config.weights.items():
        raw = criteria_scores.get(name, 0.0)
        score = max(0.0, min(1.0, raw))
        passed = score >= config.baseline
        results.append(CriterionResult(
            name=name,
            score=score,
            weight=weight,
            passed=passed,
        ))
        if name in config.fail_fast_on and score < config.baseline:
            fail_fast_blocked.append(name)

    total = sum(r.score * r.weight for r in results)
    total = round(total, 4)

    if fail_fast_blocked:
        return EvalResult(
            passed=False,
            score=total,
            baseline=config.baseline,
            criteria=results,
            fail_fast_blocked=fail_fast_blocked,
        )

    return EvalResult(
        passed=total >= config.baseline,
        score=total,
        baseline=config.baseline,
        criteria=results,
        fail_fast_blocked=[],
    )


def append_history(
    data_dir: Path,
    issue_number: int,
    result: EvalResult,
    history_max: int = HISTORY_MAX,
) -> list[dict[str, Any]]:
    path = data_dir / "score_history.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    history: list[dict[str, Any]] = []
    if path.exists():
        try:
            history = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            history = []

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "issue": issue_number,
        "score": result.score,
        "baseline": result.baseline,
        "passed": result.passed,
        "criteria": {r.name: r.score for r in result.criteria},
    }
    history.append(entry)

    if len(history) > history_max:
        history = history[-history_max:]

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    tmp.rename(path)

    return history
