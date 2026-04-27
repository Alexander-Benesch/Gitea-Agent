from __future__ import annotations

import hashlib
from typing import Any


def ai_attribution_trailer(model: str, version: str = "") -> str:
    model_id = f"{model}@{version}" if version else model
    return f"AI-Generated-By: {model_id}"


def enrich_llm_event_payload(
    payload: dict[str, Any],
    *,
    prompt: str = "",
    system_prompt_version: str = "",
    temperature: float | None = None,
    model_version: str = "",
) -> dict[str, Any]:
    enriched = dict(payload)
    if prompt:
        enriched["prompt_hash"] = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    if system_prompt_version:
        enriched["system_prompt_version"] = system_prompt_version
    if temperature is not None:
        enriched["temperature"] = temperature
    if model_version:
        enriched["model_version"] = model_version
    return enriched


RISK_CLASSIFICATION = {
    "system": "S.A.M.U.E.L.",
    "classification": "Limited Risk",
    "article": "Art. 6, Art. 50 EU AI Act (VO 2024/1689)",
    "justification": (
        "S.A.M.U.E.L. generiert Code-Vorschlaege unter menschlicher Aufsicht. "
        "Kein autonomes Handeln ohne Gate-Approval. Kein High-Risk-Anwendungsfall "
        "(nicht in Annex III gelistet). Transparenzpflichten (Art. 50) werden durch "
        "AI-Attribution-Trailer und Audit-Trail erfuellt."
    ),
    "transparency_measures": [
        "AI-Generated-By Git-Trailer in jedem KI-generierten Commit",
        "LLMCallCompleted-Events mit prompt_hash und model_version",
        "14 PR-Gates als Human-Oversight-Mechanismus",
        "Audit-Trail mit Correlation-IDs fuer Rueckverfolgbarkeit",
    ],
    "human_oversight": [
        "Gate-System: Kein PR ohne 14 Pruefungen",
        "Plan-Approval: Mensch kann Plan ablehnen/aendern",
        "Watch-Mode: Semaphore-kontrollierte Parallelitaet",
        "Self-Mode: Zusaetzliche Parity-Tests",
    ],
}


def get_risk_classification() -> dict[str, Any]:
    return dict(RISK_CLASSIFICATION)
