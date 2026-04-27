"""Dashboard data aggregation layer."""
from __future__ import annotations

import json
import logging
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def load_audit_events(data_dir: str = "data", limit: int = 200) -> list[dict]:
    """Load recent events from agent.jsonl audit log."""
    log_path = Path(data_dir) / "logs" / "agent.jsonl"
    if not log_path.exists():
        return []
    events = []
    try:
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines[-limit:]:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        log.warning("Failed to read audit log: %s", log_path)
    return events


def get_log_entries(data_dir: str = "data", limit: int = 200) -> list[dict]:
    """Get formatted log entries for the log viewer."""
    events = load_audit_events(data_dir, limit)
    entries = []
    for evt in events:
        payload = evt.get("payload", {})
        entries.append({
            "ts": evt.get("ts", ""),
            "level": _classify_level(evt),
            "category": _classify_category(evt),
            "event": payload.get("message_name", evt.get("name", "")),
            "message": _build_message(evt),
            "issue": payload.get("issue", ""),
            "correlation_id": payload.get("correlation_id", ""),
            "owasp": payload.get("owasp_risk", ""),
        })
    return list(reversed(entries))


def get_security_overview(data_dir: str = "data") -> dict[str, Any]:
    """OWASP Agentic AI risk overview from audit events."""
    events = load_audit_events(data_dir, 500)

    owasp_risks = {
        "A01": {"name": "Unrestricted Agency", "events": 0, "last": ""},
        "A02": {"name": "Uncontrolled Agentic Behavior", "events": 0, "last": ""},
        "A03": {"name": "Inadequate Sandboxing", "events": 0, "last": ""},
        "A04": {"name": "Broken Trust Boundaries", "events": 0, "last": ""},
        "A05": {"name": "Identity & Access Abuse", "events": 0, "last": ""},
        "A06": {"name": "Unmonitored Agent Activities", "events": 0, "last": ""},
        "A07": {"name": "Unsafe Tool/API Integration", "events": 0, "last": ""},
        "A08": {"name": "Excessive Autonomy", "events": 0, "last": ""},
        "A09": {"name": "Inadequate Feedback Loops", "events": 0, "last": ""},
        "A10": {"name": "Opaque Agent Reasoning", "events": 0, "last": ""},
    }

    barriers = []
    for evt in events:
        payload = evt.get("payload", {})
        owasp = payload.get("owasp_risk", "")
        if owasp:
            risk_key = owasp.split(":")[0] if ":" in owasp else owasp
            if risk_key in owasp_risks:
                owasp_risks[risk_key]["events"] += 1
                owasp_risks[risk_key]["last"] = evt.get("ts", "")

        msg_name = payload.get("message_name", "")
        if msg_name in ("GateFailed", "SecurityTripwireTriggered", "WorkflowAborted"):
            barriers.append({
                "ts": evt.get("ts", ""),
                "issue": payload.get("issue", ""),
                "gate": payload.get("gate", msg_name),
                "action": "blocked" if msg_name == "GateFailed" else "warn",
                "owasp": owasp,
                "detail": payload.get("reason", ""),
            })

    total = len(events)
    classified = sum(1 for e in events if e.get("payload", {}).get("owasp_risk"))
    active_risks = sum(1 for r in owasp_risks.values() if r["events"] > 0)

    return {
        "total_events": total,
        "classified_pct": round(classified / total * 100) if total else 0,
        "active_risks": active_risks,
        "risks": owasp_risks,
        "barriers": barriers[-30:],
    }


def get_workflow_issues(data_dir: str = "data") -> list[dict]:
    """Get issue processing status from audit events."""
    events = load_audit_events(data_dir, 500)
    issues: dict[int, dict] = {}

    for evt in events:
        payload = evt.get("payload", {})
        issue_num = payload.get("issue")
        if not issue_num:
            continue
        issue_num = int(issue_num)

        if issue_num not in issues:
            issues[issue_num] = {
                "number": issue_num,
                "events": [],
                "status": "unknown",
                "last_event": "",
                "last_ts": "",
            }

        msg_name = payload.get("message_name", "")
        issues[issue_num]["events"].append({
            "name": msg_name,
            "ts": evt.get("ts", ""),
            "detail": payload.get("reason", ""),
        })
        issues[issue_num]["last_event"] = msg_name
        issues[issue_num]["last_ts"] = evt.get("ts", "")

        # Determine status from event
        if msg_name == "PRCreated":
            issues[issue_num]["status"] = "pr_created"
        elif msg_name in ("WorkflowBlocked", "WorkflowAborted", "GateFailed"):
            issues[issue_num]["status"] = "blocked"
        elif msg_name == "CodeGenerated":
            issues[issue_num]["status"] = "implemented"
        elif msg_name == "PlanCreated":
            issues[issue_num]["status"] = "planned"
        elif msg_name == "IssueReady":
            issues[issue_num]["status"] = "ready"

    return sorted(issues.values(), key=lambda x: x.get("last_ts", ""), reverse=True)[:30]


def get_llm_usage(data_dir: str = "data") -> dict[str, Any]:
    """Get LLM token usage and cost statistics."""
    events = load_audit_events(data_dir, 500)

    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    by_task: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})

    for evt in events:
        payload = evt.get("payload", {})
        msg_name = payload.get("message_name", "")
        if msg_name == "LLMCallCompleted":
            total_calls += 1
            tokens = payload.get("tokens", 0) or payload.get("input_tokens", 0) + payload.get("output_tokens", 0)
            cost = payload.get("cost", 0.0)
            task = payload.get("task", "default")
            total_tokens += tokens
            total_cost += cost
            by_task[task]["calls"] += 1
            by_task[task]["tokens"] += tokens
            by_task[task]["cost"] += cost

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "by_task": dict(by_task),
    }


def get_branches() -> list[dict]:
    """Get git branch overview."""
    branches = []
    try:
        result = subprocess.run(
            ["git", "branch", "--format=%(refname:short) %(upstream:trackshort) %(committerdate:relative)"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.strip().split(" ", 2)
                if parts and parts[0] and parts[0] != "main":
                    branches.append({
                        "name": parts[0],
                        "track": parts[1] if len(parts) > 1 else "",
                        "age": parts[2] if len(parts) > 2 else "",
                    })
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return branches


KNOWN_FEATURE_FLAGS: list[tuple[str, str, bool]] = [
    ("eval", "Evaluation nach jedem Implement", True),
    ("watch", "Watch-Modus (Polling)", True),
    ("healing", "Self-Healing bei Eval-Fail", False),
    ("auto_issues", "Automatische Issue-Erstellung", False),
    ("changelog", "Changelog-Generierung", False),
    ("auto_implement_llm", "Auto-Implement via LLM", True),
    ("auto_merge_pr", "Auto-Merge nach Gates", False),
    ("hallucination_guard", "Hallucination-Guard", True),
    ("sequence_validator", "Sequence-Validator", True),
    ("scope_guard", "Scope-Guard", True),
    ("acceptance_check", "AC-Verifikation", True),
    ("llm_attribution", "AI-Attribution in Commits", True),
    ("health_checks", "Health-Checks bei Start", True),
]


def get_feature_flags(config) -> list[dict]:
    """Get all feature flags with current state."""
    flags = []
    for key, desc, default in KNOWN_FEATURE_FLAGS:
        flags.append({
            "key": key,
            "enabled": config.feature_flag(key) if config else default,
            "description": desc,
        })
    return flags


LLM_TASK_NAMES: list[str] = [
    "implementation",
    "planning",
    "pr_review",
    "issue_analysis",
    "healing",
    "log_analysis",
    "docs",
    "deep_coding",
    "test_generation",
]


def get_llm_routing(config) -> list[dict]:
    """Return provider/model per task.

    Falls ``llm.tasks.<task>.provider/model`` not set, falls back to
    ``llm.default.provider/model``. If no task-specific entries exist at all,
    returns a single ``default`` row.
    """
    if config is None:
        return [{"task": "default", "provider": "-", "model": "-"}]

    default_provider = config.get("llm.default.provider", "-")
    default_model = config.get("llm.default.model", "-")
    # If no explicit default model, try to infer from provider node
    if default_model == "-" and default_provider != "-":
        default_model = config.get(f"llm.{default_provider}.model", "-")

    rows: list[dict] = []
    any_task_specific = False
    for task in LLM_TASK_NAMES:
        prov = config.get(f"llm.tasks.{task}.provider")
        mdl = config.get(f"llm.tasks.{task}.model")
        if prov is not None or mdl is not None:
            any_task_specific = True
            rows.append({
                "task": task,
                "provider": prov if prov is not None else default_provider,
                "model": mdl if mdl is not None else default_model,
            })

    if not any_task_specific:
        return [{"task": "default", "provider": default_provider, "model": default_model}]
    return rows


_TAMPER_MSG_NAMES: set[str] = {
    "TamperDetected",
    "UnauthorizedChange",
    "IntegrityViolation",
}


def get_tamper_events(data_dir: str = "data", limit: int = 20) -> list[dict]:
    """Return tamper / integrity / broken trust boundary events.

    Includes payload message_name in {TamperDetected, UnauthorizedChange,
    IntegrityViolation} OR owasp_risk == ``broken_trust_boundaries``.
    Newest first, capped at ``limit``.
    """
    events = load_audit_events(data_dir, 500)
    matches: list[dict] = []
    for evt in events:
        payload = evt.get("payload", {}) or {}
        msg_name = payload.get("message_name", "")
        owasp = str(payload.get("owasp_risk", "")).lower()
        if msg_name in _TAMPER_MSG_NAMES or "broken_trust_boundaries" in owasp:
            matches.append({
                "ts": evt.get("ts", ""),
                "event": msg_name or evt.get("name", ""),
                "owasp": payload.get("owasp_risk", ""),
                "detail": payload.get("reason", "") or payload.get("detail", ""),
                "issue": payload.get("issue", ""),
            })
    matches.reverse()
    return matches[:limit]


def _classify_level(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    if name in ("GateFailed", "WorkflowAborted", "WorkflowBlocked", "SecurityTripwireTriggered", "ImplementationFailed"):
        return "error"
    if name in ("HealingFailed", "QualityFailed", "EvalFailed", "TokenLimitHit"):
        return "warn"
    return "info"


def _classify_category(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    categories = {
        "PlanCreated": "workflow", "PlanValidated": "workflow", "PlanBlocked": "workflow",
        "CodeGenerated": "workflow", "PRCreated": "workflow", "IssueReady": "workflow",
        "GateFailed": "gates", "SecurityTripwireTriggered": "security",
        "LLMCallCompleted": "llm", "LLMUnavailable": "llm",
        "EvalCompleted": "eval", "EvalFailed": "eval",
        "HealthCheck": "system", "ConfigReloaded": "config",
        "HealingFailed": "workflow", "QualityFailed": "quality",
        "WorkflowAborted": "workflow", "WorkflowBlocked": "workflow",
    }
    return categories.get(name, "system")


def _build_message(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    reason = payload.get("reason", "")
    if reason:
        return f"{name}: {reason}"
    return name
