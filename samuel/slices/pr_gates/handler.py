from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, CreatePRCommand
from samuel.core.config import GatesConfigSchema, load_gates_config
from samuel.core.events import GateFailedEvent, PRCreated
from samuel.core.ports import IExternalGate, IVersionControl
from samuel.core.types import GateContext, GateResult
from samuel.slices.pr_gates.gates import GATE_REGISTRY

log = logging.getLogger(__name__)


class PRGatesHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config_dir: str | Path = "config",
        external_gates: list[IExternalGate] | None = None,
        ai_attribution_fn: Callable[[], str] | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._external_gates = external_gates or []
        self._ai_attribution_fn = ai_attribution_fn
        try:
            self._gates_config = load_gates_config(config_dir)
        except ValueError:
            self._gates_config = GatesConfigSchema()

    @staticmethod
    def _get_branch_diff(branch: str, base: str) -> tuple[list[str], str]:
        """Get changed files and diff between branch and base via git."""
        changed_files: list[str] = []
        diff = ""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{base}...{branch}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                changed_files = [f for f in result.stdout.strip().split("\n") if f]
            result = subprocess.run(
                ["git", "diff", f"{base}...{branch}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                diff = result.stdout[:50000]  # Max 50KB diff for gate checks
        except (subprocess.TimeoutExpired, FileNotFoundError):
            log.warning("Failed to get git diff for %s...%s", base, branch)
        return changed_files, diff

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, CreatePRCommand)
        issue_number = cmd.issue_number
        correlation_id = cmd.correlation_id or ""

        changed_files, diff = self._get_branch_diff(cmd.branch, cmd.base or "main")
        ctx = GateContext(
            issue_number=issue_number,
            branch=cmd.branch,
            changed_files=changed_files,
            diff=diff,
        )

        if self._scm:
            comments = self._scm.get_comments(issue_number)
            for c in reversed(comments):
                if "## Plan" in c.body or "Agent-Metadaten" in c.body:
                    ctx = GateContext(
                        issue_number=issue_number,
                        branch=cmd.branch,
                        changed_files=ctx.changed_files,
                        diff=ctx.diff,
                        plan_comment=c.body,
                    )
                    break

        results: list[GateResult] = []
        blocked = False

        all_gate_ids = set(self._gates_config.required) | set(self._gates_config.optional)
        disabled = set(self._gates_config.disabled)
        active_gates = all_gate_ids - disabled

        for gate_id in sorted(active_gates, key=lambda x: (isinstance(x, str), str(x))):
            gate_fn = GATE_REGISTRY.get(gate_id)
            if not gate_fn:
                continue

            result = gate_fn(ctx)
            results.append(result)

            if not result.passed:
                is_required = gate_id in self._gates_config.required

                if is_required:
                    blocked = True
                    self._bus.publish(GateFailedEvent(
                        payload={
                            "issue": issue_number,
                            "gate": gate_id,
                            "reason": result.reason,
                            "owasp_risk": result.owasp_risk,
                        },
                        correlation_id=correlation_id,
                    ))

        for ext_gate in self._external_gates:
            try:
                ext_result = ext_gate.run(ctx)
                results.append(ext_result)
                if not ext_result.passed:
                    blocked = True
                    self._bus.publish(GateFailedEvent(
                        payload={
                            "issue": issue_number,
                            "gate": ext_gate.name,
                            "reason": ext_result.reason,
                            "external": True,
                        },
                        correlation_id=correlation_id,
                    ))
            except Exception as exc:
                log.warning("External gate %s failed: %s", ext_gate.name, exc)
                blocked = True
                self._bus.publish(GateFailedEvent(
                    payload={
                        "issue": issue_number,
                        "gate": ext_gate.name,
                        "reason": f"External gate error: {exc}",
                        "external": True,
                    },
                    correlation_id=correlation_id,
                ))

        if blocked:
            return {
                "passed": False,
                "results": results,
                "blocked_gates": [r for r in results if not r.passed],
            }

        attribution = self._ai_attribution_fn() if self._ai_attribution_fn else None

        # Actually create the PR on SCM
        pr_result = None
        if self._scm:
            try:
                title = f"feat: Issue #{issue_number}"
                body_parts = [f"## Issue #{issue_number}"]
                if attribution:
                    body_parts.append(f"\n{attribution}")
                pr_result = self._scm.create_pr(
                    head=cmd.branch,
                    base=cmd.base or "main",
                    title=title,
                    body="\n".join(body_parts),
                )
                log.info("PR #%d created: %s", pr_result.number, pr_result.html_url)
            except Exception as exc:
                log.error("Failed to create PR: %s", exc)

        payload: dict[str, Any] = {
            "issue": issue_number,
            "branch": cmd.branch,
        }
        if pr_result:
            payload["pr_number"] = pr_result.number
            payload["pr_url"] = pr_result.html_url
        if attribution:
            payload["ai_attribution"] = attribution

        self._bus.publish(PRCreated(
            payload=payload,
            correlation_id=correlation_id,
        ))

        result: dict[str, Any] = {
            "passed": True,
            "results": results,
            "blocked_gates": [],
        }
        if pr_result:
            result["pr_number"] = pr_result.number
            result["pr_url"] = pr_result.html_url
        if attribution:
            result["ai_attribution"] = attribution
        return result
