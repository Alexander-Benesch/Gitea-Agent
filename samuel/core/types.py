from __future__ import annotations

import html as _html_mod
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser


@dataclass
class Label:
    id: int
    name: str


@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str
    labels: list[Label] = field(default_factory=list)


@dataclass
class Comment:
    id: int
    body: str
    user: str
    created_at: str = ""


@dataclass
class PR:
    id: int
    number: int
    title: str
    html_url: str
    state: str = "open"
    merged: bool = False


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    stop_reason: str = "end_turn"
    model_used: str = ""
    latency_ms: int = 0


@dataclass
class GateContext:
    issue_number: int
    branch: str
    changed_files: list[str]
    diff: str
    plan_comment: str | None = None
    eval_score: float | None = None
    pr_url: str | None = None


@dataclass
class GateResult:
    gate: int | str
    passed: bool
    reason: str
    owasp_risk: str | None = None


@dataclass
class AuditQuery:
    issue: int | None = None
    correlation_id: str | None = None
    owasp_risk: str | None = None
    event_name: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100


@dataclass
class SkeletonEntry:
    name: str
    kind: str
    file: str
    line_start: int
    line_end: int
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    language: str = ""


@dataclass
class HealCommand:
    issue: int
    failure_type: str
    context: dict = field(default_factory=dict)
    attempt: int = 1


@dataclass
class WorkflowCheckpoint:
    issue: int
    phase: str
    step: str
    state: dict = field(default_factory=dict)


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def strip_html(text: str) -> str:
    if not isinstance(text, str):
        return str(text) if text else ""
    if "<" not in text:
        return _html_mod.unescape(text).strip() if "&" in text else text
    parts: list[str] = []

    class _S(HTMLParser):
        def handle_data(self, data: str) -> None:
            parts.append(data)

    _S().feed(text)
    return _html_mod.unescape("".join(parts)).strip()


_COMMENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "plan": ["## Analyse", "## Plan", "## Risiko"],
    "completion": ["## Änderungen", "## Tests"],
    "review": ["## Review"],
}


def validate_comment(
    body: str,
    comment_type: str,
    *,
    required_fields: dict[str, list[str]] | None = None,
) -> list[str]:
    fields = (required_fields or _COMMENT_REQUIRED_FIELDS).get(comment_type, [])
    return [f for f in fields if f.lower() not in body.lower()]
