from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, EvaluateCommand
from samuel.core.config import EvalSchema, load_eval_config
from samuel.core.events import EvalCompleted, EvalFailed
from samuel.core.ports import IConfig, IVersionControl
from samuel.slices.evaluation.scoring import EvalResult, append_history, compute_score

log = logging.getLogger(__name__)


class EvaluationHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config_dir: str | Path = "config",
        data_dir: str | Path = "data",
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._data_dir = Path(data_dir)
        self._agent_config = config
        self._history_max: int = int(
            config.get("agent.eval.history_max", 90) if config else 90
        )
        try:
            self._config = load_eval_config(config_dir)
        except ValueError:
            self._config = EvalSchema()

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, EvaluateCommand)
        issue_number = cmd.issue_number
        correlation_id = cmd.correlation_id or ""

        criteria_scores: dict[str, float] = cmd.payload.get("criteria_scores", {})

        if not criteria_scores:
            self._bus.publish(EvalFailed(
                payload={
                    "issue": issue_number,
                    "reason": "no criteria_scores provided",
                },
                correlation_id=correlation_id,
            ))
            return None

        result = compute_score(criteria_scores, self._config)

        append_history(self._data_dir, issue_number, result, history_max=self._history_max)

        if result.passed:
            self._bus.publish(EvalCompleted(
                payload={
                    "issue": issue_number,
                    "score": result.score,
                    "baseline": result.baseline,
                    "criteria": {r.name: r.score for r in result.criteria},
                },
                correlation_id=correlation_id,
            ))
        else:
            self._bus.publish(EvalFailed(
                payload={
                    "issue": issue_number,
                    "score": result.score,
                    "baseline": result.baseline,
                    "fail_fast_blocked": result.fail_fast_blocked,
                    "criteria": {r.name: r.score for r in result.criteria},
                },
                correlation_id=correlation_id,
            ))

        if self._scm:
            comment = _format_eval_comment(issue_number, result)
            self._scm.post_comment(issue_number, comment)

        return {
            "passed": result.passed,
            "score": result.score,
            "baseline": result.baseline,
            "fail_fast_blocked": result.fail_fast_blocked,
            "criteria": {r.name: r.score for r in result.criteria},
        }


def _format_eval_comment(issue_number: int, result: EvalResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"## Evaluation Issue #{issue_number} — {status}",
        "",
        f"**Score:** {result.score:.1%} (Baseline: {result.baseline:.1%})",
        "",
    ]
    if result.fail_fast_blocked:
        lines.append(f"**fail_fast blockiert:** {', '.join(result.fail_fast_blocked)}")
        lines.append("")
    lines.append("| Kriterium | Score | Gewicht |")
    lines.append("|-----------|-------|---------|")
    for c in result.criteria:
        lines.append(f"| {c.name} | {c.score:.1%} | {c.weight:.0%} |")
    return "\n".join(lines)
