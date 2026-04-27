# Technische Beschreibungen — S.A.M.U.E.L. v2

Dokumentation der zentralen Pipelines. Jeder Knotenpunkt mit Input/Output,
beteiligten Dateien, Sprach-Unterstützung, Voraussetzungen und Beispielen.

**Stand:** Phase 14.11 (2026-04-17).

---

## Pipeline-Übersicht

Der vollständige E2E-Flow von Issue bis PR besteht aus 4 Pipelines, die über
das Bus-System verkettet sind:

```
┌─────────────────────────────────────────────────────────────┐
│  Issue (Gitea)                                              │
└────────────────────┬────────────────────────────────────────┘
                     │  IssueReady Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 1:  PLANNING                                      │
│                                                             │
│  PlanIssueCommand → LLM(Plan-Prompt) → validate_plan        │
│                   → Retry falls 50-80% Score                │
│                   → Post Plan als Issue-Kommentar           │
│                                                             │
│  Details: pipeline_planning.md                              │
└────────────────────┬────────────────────────────────────────┘
                     │  PlanValidated Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 2:  IMPLEMENTATION (Context-Building)             │
│                                                             │
│  ImplementCommand                                           │
│   → K1 Issue laden                                          │
│   → K2-K11 Context bauen (Keywords, Skeleton, Grep, ...)    │
│   → K12 Prompt-Assembly                                     │
│   → K13 Validator-Gate                                      │
│   → K14 LLM-Loop (5 Runden, Retry mit echtem Code)          │
│   → K15 Patches anwenden                                    │
│   → K16 Git commit + Branch-Push                            │
│                                                             │
│  Details: pipeline_issue_to_llm.md                          │
└────────────────────┬────────────────────────────────────────┘
                     │  CodeGenerated Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 3:  EVALUATION                                    │
│                                                             │
│  EvaluateCommand                                            │
│   → E3 compute_score (gewichtete Kriterien)                 │
│   → E4 fail_fast Hard-Blocks                                │
│   → E5 History persistieren (data/eval_history/)            │
│   → E6 Event + Markdown-Comment                             │
│                                                             │
│  Details: pipeline_evaluation.md                            │
└────────────────────┬────────────────────────────────────────┘
                     │  EvalCompleted Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 4:  PR-GATES                                      │
│                                                             │
│  CreatePRCommand                                            │
│   → G1 git diff ermitteln                                   │
│   → G4 13 Gates (Branch/Plan/Scope/Slice/Quality/...)       │
│   → G5 External-Gate-Plugins                                │
│   → G6 scm.create_pr()                                      │
│                                                             │
│  Details: pipeline_pr_gates.md                              │
└────────────────────┬────────────────────────────────────────┘
                     │  PRCreated Event
                     ▼
                   PR auf Gitea/GitHub
```

---

## Pipeline-Dokumente

| Pipeline | Datei | Knoten | Stand |
|---|---|---|---|
| 1. Planning | [pipeline_planning.md](pipeline_planning.md) | P1-P10 | ✓ 14.11 |
| 2. Implementation (Context→LLM) | [pipeline_issue_to_llm.md](pipeline_issue_to_llm.md) | K1-K16 | ✓ 14.11 |
| 3. Evaluation | [pipeline_evaluation.md](pipeline_evaluation.md) | E1-E6 | ✓ 14.11 (mit Gap-Notiz) |
| 4. PR-Gates | [pipeline_pr_gates.md](pipeline_pr_gates.md) | G0-G6, 13 Gates | ✓ 14.11 |

---

## Übergreifende Komponenten (nicht Pipeline-spezifisch)

Diese Module werden von mehreren Pipelines genutzt:

| Komponente | Datei | Zweck |
|---|---|---|
| Event-Bus | `samuel/core/bus.py` | Pub/Sub + Command-Dispatch, Middlewares (Audit/Security/Idempotency) |
| WorkflowEngine | `samuel/core/workflow.py` | Liest `config/workflows/*.json`, verdrahtet Events→Commands |
| SCM-Adapter | `samuel/adapters/gitea/`, `adapters/github/` | Issue/Comment/PR/Label API |
| LLM-Adapter | `samuel/adapters/llm/` | Provider-Abstraction (DeepSeek/Claude/Ollama/LMStudio) |
| Audit-Trail | `samuel/slices/audit_trail/` | OWASP-Klassifikation + JSONL-Log |
| Architecture | `samuel/slices/architecture/` | Konfig-getriebene Scope-Regeln |
| Labels | `samuel/slices/labels/` | Workflow-Label-Transitions |

---

## Bekannte Gaps (Stand 14.11)

Bereits als Gitea-Issues erfasst:

- **#152** — Skeleton-as-TOC + Slice-Request-Loop
  - K10 Fallback für große Files ohne Anker
- **#153** — LLM-Qualitätskontrolle (gemessene Gewichtung)
  - Per-(Provider, Model, Task) Score-History, Routing-Feedback
- **Evaluation Test-Runner nicht verdrahtet** (in `pipeline_evaluation.md` dokumentiert)
  - v1 hatte HTTP-Server-Tests + Multi-Language-Fallback

---

## Lese-Tipps nach Persona

**Neueinsteiger:** Lies in dieser Reihenfolge:
1. Diese README (Übersicht)
2. `pipeline_planning.md` (einfachste Pipeline, 2 LLM-Calls max)
3. `pipeline_issue_to_llm.md` (die komplexeste, Herzstück)
4. `pipeline_pr_gates.md` (Regeln + Gates)
5. `pipeline_evaluation.md` (Scoring-Logik)

**Debugger eines schlechten LLM-Outputs:**
Starte in `pipeline_issue_to_llm.md` bei K13 (Validator) und arbeite rückwärts.

**Erweiterung um neue Sprache:**
Siehe `pipeline_issue_to_llm.md` Abschnitt "K7 Skeleton-Builders" + Registry.

**Neues Gate für PR:**
Siehe `pipeline_pr_gates.md` → Gate in `samuel/slices/pr_gates/gates.py` anlegen + in `GATE_REGISTRY` eintragen.

**Neue Architektur-Regel:**
`config/architecture.json` bearbeiten — keine Code-Änderung nötig. Siehe K5 in `pipeline_issue_to_llm.md`.

---

## Konfigurations-Dateien

Zentrale Config-Dateien die Pipeline-Verhalten steuern:

| Datei | Schema | Zweck |
|---|---|---|
| `config/agent.json` | - | Mode, exclude_dirs, Context-Limits |
| `config/architecture.json` | - | Rollen + Scopes (Pipeline 2, K5) |
| `config/features.json` | - | Feature-Flags |
| `config/labels.json` | - | Workflow-Labels (Seeded via `samuel setup-labels`) |
| `config/gates.json` | `GatesConfigSchema` | Required/Optional/Disabled Gates (Pipeline 4) |
| `config/eval.json` | `EvalSchema` | Kriterien + Gewichte (Pipeline 3) |
| `config/llm.json` + `config/llm/*.json` | - | Provider + Routing |
| `config/workflows/*.json` | - | Workflow-Definitionen (Events↔Commands) |
| `config/hooks.json` | - | Quality-Checks-Registry |
| `config/audit.json` | - | JSONL-Sink-Config |
| `config/notifications.json` | - | Notification-Sinks |
| `config/privacy.json` | - | DSGVO-Regionen, Retention |
| `config/repo_patterns.json` | - | Sequence-Validator Patterns |

---

## Pflege-Regel

Bei Pipeline-Änderungen: **Zuerst Code, dann Doc — im gleichen PR**.
Ein Pipeline-Doc ist nur dann wertvoll, wenn es aktuell ist.

Wenn die Pipeline erweitert wird (z.B. neuer Knoten K17 / P11), diese README
um die Übersicht aktualisieren und den jeweiligen Pipeline-Datei-Eintrag
ergänzen.

---

*Erstellt: 2026-04-17. Stand Phase 14.11.*
