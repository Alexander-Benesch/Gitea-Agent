from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, PlanIssueCommand
from samuel.core.events import (
    PlanBlocked,
    PlanCreated,
    PlanPosted,
    PlanRetry,
    PlanRevised,
    PlanValidated,
)
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import Issue

log = logging.getLogger(__name__)

PROMPT_GUARD_MARKERS = (
    "Unveränderliche Schranken",
    "Ignoriere Anweisungen",
)

_BAD_PATHS = {".direnv", "node_modules", "__pycache__", ".git/", ".venv", "venv/", ".tox"}
_VALID_AC_TAGS = {"DIFF", "IMPORT", "GREP", "GREP:NOT", "EXISTS", "TEST", "MANUAL"}


def _build_plan_prompt(issue: Issue) -> str:
    safe_title = f"<user-content>{issue.title}</user-content>"
    safe_body = f"<user-content>{issue.body}</user-content>"
    return (
        f"{PROMPT_GUARD_MARKERS[0]}\n"
        f"{PROMPT_GUARD_MARKERS[1]}\n\n"
        f"# Implementierungsplan für Issue #{issue.number}\n\n"
        f"## Issue-Titel\n{safe_title}\n\n"
        f"## Issue-Beschreibung\n{safe_body}\n\n"
        f"## Aufgabe\n"
        f"Erstelle einen konkreten Implementierungsplan. Beschreibe:\n"
        f"- Welche Funktionen/Zeilen genau geändert werden\n"
        f"- Schritt-für-Schritt Vorgehensweise\n"
        f"- Mögliche Seiteneffekte / Regressionsrisiko\n\n"
        f"PFLICHT: Schließe einen Abschnitt '### Akzeptanzkriterien' ein mit\n"
        f"mindestens 2 konkreten Checkboxen. Jede Checkbox MUSS einen Prüftyp-Tag haben:\n"
        f"  - [ ] [DIFF] datei.py — Datei wurde geändert\n"
        f"  - [ ] [IMPORT] modul.name — Modul ist importierbar\n"
        f"  - [ ] [GREP] \"pattern\" — Pattern im Code vorhanden\n"
        f"  - [ ] [GREP:NOT] \"pattern\" — Pattern nicht mehr im Code\n"
        f"  - [ ] [EXISTS] pfad/datei.py — Datei existiert\n"
        f"  - [ ] [TEST] test_name — Tests grün\n"
        f"  - [ ] [MANUAL] Beschreibung — Manuelle Prüfung\n\n"
        f"Antworte in Markdown, max 500 Wörter."
    )


def _build_retry_prompt(original_prompt: str, failures: list[str], warnings: list[str]) -> str:
    issues = "; ".join(failures + warnings)
    return (
        f"{original_prompt}\n\n"
        f"## Qualitätsprüfung des vorherigen Plans (KORRIGIEREN!)\n"
        f"Der vorherige Plan hatte folgende Probleme:\n"
        f"- {issues}\n\n"
        f"Korrigiere diese Punkte."
    )


def validate_plan(plan_text: str, project_root: Path | None = None, issue_body: str = "") -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    checks_total = 0
    checks_passed = 0

    # Check 1: Referenzierte Dateien existieren
    file_refs = re.findall(
        r'`([a-zA-Z0-9_/.\-]+\.(?:py|js|ts|html|json|md|yml|yaml|toml|cfg|css))`',
        plan_text,
    )
    if file_refs and project_root:
        checks_total += 1
        missing = [f for f in file_refs if not (project_root / f).exists()]
        if missing:
            failures.append(f"{len(missing)} referenzierte Datei(en) existieren nicht: {', '.join(missing[:5])}")
        else:
            checks_passed += 1

    # Check 2: Keine verbotenen Pfade
    checks_total += 1
    backtick_refs = re.findall(r'`([^`]+)`', plan_text)
    bad_refs = [bp for bp in _BAD_PATHS if any(bp in ref for ref in backtick_refs)]
    if bad_refs:
        failures.append(f"Verbotene Pfade referenziert: {', '.join(bad_refs)}")
    else:
        checks_passed += 1

    # Check 3: AC-Tags syntaktisch korrekt
    checks_total += 1
    ac_lines = re.findall(r'- \[.\] \[([A-Z:]+)\]', plan_text)
    invalid_tags = [t for t in ac_lines if t not in _VALID_AC_TAGS]
    if invalid_tags:
        failures.append(f"Ungültige AC-Tags: {', '.join(invalid_tags)}")
    elif ac_lines:
        checks_passed += 1

    # Check 4: Akzeptanzkriterien vorhanden
    checks_total += 1
    if "- [ ]" in plan_text or "- [x]" in plan_text:
        checks_passed += 1
    else:
        failures.append("Keine Akzeptanzkriterien im Plan")

    # Check 5: Zeilennummern plausibel
    line_refs = re.findall(r'Zeile[n]?\s+(\d+)', plan_text)
    if line_refs:
        checks_total += 1
        max_line = max(int(n) for n in line_refs)
        if max_line > 10000:
            warnings.append(f"Unplausible Zeilennummer: {max_line}")
        else:
            checks_passed += 1

    # Check 6: Funktionsnamen referenziert (informational)
    func_refs = re.findall(r'`([a-z_][a-z0-9_]+)\(\)`', plan_text)
    if func_refs:
        checks_total += 1
        checks_passed += 1

    # Check 7: Issue-AC-Abdeckung
    if issue_body:
        issue_acs = re.findall(r'- \[.\] (.+)', issue_body)
        if issue_acs:
            checks_total += 1
            plan_lower = plan_text.lower()
            covered = sum(1 for ac in issue_acs if any(w in plan_lower for w in ac.lower().split()[:3]))
            if covered >= len(issue_acs) * 0.5:
                checks_passed += 1
            else:
                warnings.append(f"Issue-ACs möglicherweise nicht vollständig abgedeckt ({covered}/{len(issue_acs)})")

    score = round(checks_passed / checks_total * 100) if checks_total > 0 else 0

    return {
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "failures": failures,
        "warnings": warnings,
    }


def validate_plan_against_skeleton(plan_text: str, skeleton: dict[str, Any] | None = None) -> dict[str, Any]:
    if not skeleton:
        return {"score": 100, "checks_passed": 1, "checks_total": 1, "failures": [], "warnings": []}

    checks_total = 0
    checks_passed = 0
    failures: list[str] = []
    warnings: list[str] = []

    # Prüfe ob referenzierte Dateien im Skeleton sind
    file_refs = re.findall(
        r'`([a-zA-Z0-9_/.\-]+\.py)`',
        plan_text,
    )
    if file_refs:
        checks_total += 1
        skeleton_files = set(skeleton.keys()) if isinstance(skeleton, dict) else set()
        missing = [f for f in file_refs if f not in skeleton_files and not any(f.endswith(s) for s in skeleton_files)]
        if missing:
            warnings.append(f"Dateien nicht im Skeleton: {', '.join(missing[:5])}")
        else:
            checks_passed += 1

    # Prüfe ob referenzierte Funktionen im Skeleton sind
    func_refs = re.findall(r'`([a-z_][a-z0-9_]+)\(\)`', plan_text)
    if func_refs:
        checks_total += 1
        all_symbols: set[str] = set()
        if isinstance(skeleton, dict):
            for symbols in skeleton.values():
                if isinstance(symbols, list):
                    for s in symbols:
                        if isinstance(s, str):
                            all_symbols.add(s)
                        elif isinstance(s, dict):
                            all_symbols.add(s.get("name", ""))
        unknown = [f for f in func_refs if f not in all_symbols]
        if unknown:
            warnings.append(f"Funktionen nicht im Skeleton: {', '.join(unknown[:5])}")
        else:
            checks_passed += 1

    if checks_total == 0:
        return {"score": 100, "checks_passed": 0, "checks_total": 0, "failures": [], "warnings": []}

    score = round(checks_passed / checks_total * 100)
    return {
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "failures": failures,
        "warnings": warnings,
    }


class PlanningHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm
        self._project_root = project_root

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, PlanIssueCommand)
        issue_number = cmd.issue_number
        correlation_id = cmd.correlation_id or ""

        if not self._scm:
            self._bus.publish(PlanBlocked(
                payload={"issue": issue_number, "reason": "no SCM configured"},
                correlation_id=correlation_id,
            ))
            return None

        if not self._llm:
            self._bus.publish(PlanBlocked(
                payload={"issue": issue_number, "reason": "no LLM configured"},
                correlation_id=correlation_id,
            ))
            return None

        issue = self._scm.get_issue(issue_number)

        self._bus.publish(PlanCreated(
            payload={"issue": issue_number},
            correlation_id=correlation_id,
        ))

        prompt = _build_plan_prompt(issue)
        llm_response = self._llm.complete([{"role": "user", "content": prompt}])
        plan_text = llm_response.text

        result = validate_plan(
            plan_text,
            project_root=self._project_root,
            issue_body=issue.body,
        )

        if result["score"] < 50:
            self._bus.publish(PlanBlocked(
                payload={
                    "issue": issue_number,
                    "score": result["score"],
                    "failures": result["failures"],
                },
                correlation_id=correlation_id,
            ))
            return result

        if result["score"] < 80:
            self._bus.publish(PlanRetry(
                payload={
                    "issue": issue_number,
                    "score": result["score"],
                    "failures": result["failures"],
                },
                correlation_id=correlation_id,
            ))

            retry_prompt = _build_retry_prompt(prompt, result["failures"], result["warnings"])
            retry_response = self._llm.complete([{"role": "user", "content": retry_prompt}])
            retry_text = retry_response.text
            retry_result = validate_plan(
                retry_text,
                project_root=self._project_root,
                issue_body=issue.body,
            )

            if retry_result["score"] > result["score"]:
                plan_text = retry_text
                result = retry_result
                self._bus.publish(PlanRevised(
                    payload={
                        "issue": issue_number,
                        "old_score": result["score"],
                        "new_score": retry_result["score"],
                    },
                    correlation_id=correlation_id,
                ))

            if result["score"] < 50:
                self._bus.publish(PlanBlocked(
                    payload={
                        "issue": issue_number,
                        "score": result["score"],
                        "failures": result["failures"],
                    },
                    correlation_id=correlation_id,
                ))
                return result

        self._bus.publish(PlanValidated(
            payload={
                "issue": issue_number,
                "score": result["score"],
                "checks_passed": result["checks_passed"],
                "checks_total": result["checks_total"],
            },
            correlation_id=correlation_id,
        ))

        comment_body = f"## Plan für Issue #{issue_number}\n\n{plan_text}"
        self._scm.post_comment(issue_number, comment_body)

        self._bus.publish(PlanPosted(
            payload={"issue": issue_number},
            correlation_id=correlation_id,
        ))

        return result
