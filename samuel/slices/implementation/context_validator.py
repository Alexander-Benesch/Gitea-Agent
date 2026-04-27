"""Pre-LLM Validator: prüft Context-Qualität VOR dem LLM-Call.

Vermeidet, dass der LLM mit zu dünnem oder zu fettem Kontext gerufen wird.
Ersetzt nicht den Eval-Slice (der läuft POST-Implementation), sondern
fängt offensichtliche Probleme früh ab.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextValidation:
    ok: bool
    issues: list[str]
    warnings: list[str]
    prompt_tokens_est: int
    breakdown: dict[str, int]


MIN_PROMPT_TOKENS = 200
MAX_PROMPT_TOKENS = 80_000
WARN_PROMPT_TOKENS = 30_000

MIN_SKELETON_CHARS = 50
MIN_PLAN_FILES = 0


def validate_context(
    *,
    issue_title: str,
    issue_body: str,
    plan_text: str,
    context: dict[str, str],
    prompt: str,
) -> ContextValidation:
    """Prüft ob der zusammengebaute Context ausreichend UND nicht zu groß ist."""
    issues: list[str] = []
    warnings: list[str] = []

    if not issue_title.strip():
        issues.append("Issue title is empty")
    if len(issue_body.strip()) < 20:
        issues.append(f"Issue body too short ({len(issue_body)} chars) — LLM cannot implement blind")

    breakdown = {k: len(v) for k, v in context.items()}

    has_skeleton = len(context.get("skeleton", "")) >= MIN_SKELETON_CHARS
    has_plan_files = len(context.get("plan_files", "").strip()) > 0
    has_relevant_files = len(context.get("relevant_files", "").strip()) > 0
    has_grep = len(context.get("grep", "").strip()) > 0
    has_plan = len(plan_text.strip()) > 0

    if not (has_skeleton or has_plan_files or has_relevant_files or has_grep):
        issues.append("No code context found at all (no skeleton matches, no plan-files, no grep hits)")
    elif not has_plan_files and not has_relevant_files:
        warnings.append("No concrete files loaded — LLM may hallucinate file paths")

    if not has_plan:
        warnings.append("No plan text found — LLM has no structured guidance")

    tokens_est = len(prompt) // 4

    if tokens_est < MIN_PROMPT_TOKENS:
        issues.append(f"Prompt too small ({tokens_est} tokens) — likely missing context")
    if tokens_est > MAX_PROMPT_TOKENS:
        issues.append(
            f"Prompt too large ({tokens_est} tokens > {MAX_PROMPT_TOKENS}) — "
            "compaction required before LLM call"
        )
    elif tokens_est > WARN_PROMPT_TOKENS:
        warnings.append(f"Prompt is large ({tokens_est} tokens) — consider compaction")

    return ContextValidation(
        ok=(len(issues) == 0),
        issues=issues,
        warnings=warnings,
        prompt_tokens_est=tokens_est,
        breakdown=breakdown,
    )
