from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.slices.implementation.patch_parser import get_applier, parse_patches

log = logging.getLogger(__name__)

MAX_ROUNDS = 5
MAX_EXCERPT_LINES = 200


def _load_file_excerpt_for_patch(project_root: Path, patch: dict[str, Any]) -> str:
    rel = patch.get("file", "")
    if not rel:
        return ""
    file_path = project_root / rel
    if not file_path.exists() or not file_path.is_file():
        return f"(Datei {rel} existiert nicht — nutze `## WRITE: {rel}` Format)"
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(Datei konnte nicht gelesen werden: {exc})"

    lines = content.splitlines()
    if patch.get("type") == "replace_lines" and patch.get("lines"):
        start, end = patch["lines"]
        context_start = max(1, start - 10)
        context_end = min(len(lines), end + 10)
    elif patch.get("search"):
        search_first = patch["search"].splitlines()[0] if patch["search"] else ""
        hit = None
        for i, line in enumerate(lines, start=1):
            if search_first and search_first.strip() in line:
                hit = i
                break
        if hit:
            context_start = max(1, hit - 10)
            context_end = min(len(lines), hit + 30)
        else:
            context_start = 1
            context_end = min(len(lines), MAX_EXCERPT_LINES)
    else:
        context_start = 1
        context_end = min(len(lines), MAX_EXCERPT_LINES)

    if context_end - context_start > MAX_EXCERPT_LINES:
        context_end = context_start + MAX_EXCERPT_LINES

    return "\n".join(
        f"{i:5d} | {lines[i-1]}" for i in range(context_start, context_end + 1)
    )


def _build_retry_prompt(
    base_prompt: str,
    round_num: int,
    failures_with_patches: list[tuple[str, dict[str, Any]]],
    project_root: Path,
) -> str:
    seen_files: set[str] = set()
    excerpts: list[str] = []
    fail_lines: list[str] = []
    for msg, patch in failures_with_patches:
        fail_lines.append(msg)
        rel = patch.get("file", "")
        if rel and rel not in seen_files:
            seen_files.add(rel)
            excerpt = _load_file_excerpt_for_patch(project_root, patch)
            if excerpt:
                excerpts.append(f"### {rel} (aktueller Zustand)\n```\n{excerpt}\n```")

    return "\n".join([
        base_prompt,
        "",
        f"## Patch-Fehler in Runde {round_num} — KORRIGIEREN",
        *(f"- {m}" for m in fail_lines),
        "",
        "## Aktueller Quellcode der betroffenen Dateien",
        "Nutze die gezeigten Zeilennummern exakt. REPLACE LINES mit genau diesen Nummern, "
        "oder SEARCH mit genau diesem Text.",
        "",
        *excerpts,
    ])


def run_llm_loop(
    llm: ILLMProvider,
    prompt: str,
    project_root: Path,
    *,
    on_round: Any = None,
    on_token_limit: Any = None,
) -> dict[str, Any]:
    all_patches_applied: list[dict] = []
    last_round_failures: list[str] = []
    total_input_tokens = 0
    total_output_tokens = 0
    current_prompt = prompt

    round_num = 0
    for round_num in range(1, MAX_ROUNDS + 1):
        response = llm.complete([{"role": "user", "content": current_prompt}])
        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens

        if response.stop_reason == "max_tokens":
            if on_token_limit:
                on_token_limit(round_num, total_input_tokens + total_output_tokens)
            return {
                "success": False,
                "reason": "token_limit",
                "round": round_num,
                "patches_applied": all_patches_applied,
                "failures": last_round_failures,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            }

        patches = parse_patches(response.text)
        if not patches:
            log.info("Runde %d: LLM lieferte keine parsbaren Patches", round_num)
            break

        round_failures_with_patches: list[tuple[str, dict[str, Any]]] = []
        round_failures: list[str] = []
        for patch in patches:
            rel = patch.get("file", "")
            file_path = project_root / rel
            applier = get_applier(file_path)

            results = applier.apply(file_path, [patch])
            ok = bool(results and results[0][0])
            if ok:
                all_patches_applied.append(patch)
            else:
                msg = results[0][1] if results else f"unknown error for {rel}"
                round_failures.append(msg)
                round_failures_with_patches.append((msg, patch))

        last_round_failures = round_failures

        if on_round:
            on_round(round_num, len(patches), len(round_failures))

        if not round_failures:
            break

        current_prompt = _build_retry_prompt(
            prompt, round_num, round_failures_with_patches, project_root,
        )
        log.info("Runde %d fehlgeschlagen (%d Patches), Retry mit echtem Code",
                 round_num, len(round_failures))

    return {
        "success": len(last_round_failures) == 0 and len(all_patches_applied) > 0,
        "reason": "complete" if not last_round_failures else "partial_failure",
        "round": min(round_num, MAX_ROUNDS) if round_num else 0,
        "patches_applied": all_patches_applied,
        "failures": last_round_failures,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
