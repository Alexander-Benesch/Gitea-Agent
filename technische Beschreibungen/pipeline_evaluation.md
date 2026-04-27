# Pipeline: Evaluation (Code → Score + History)

Nach `CodeGenerated` läuft die Evaluation mit gewichteten Kriterien-Scores
und einer Baseline-Prüfung. Ergebnis: `EvalCompleted` (PR darf erstellt werden)
oder `EvalFailed`.

**Stand:** Phase 14.11.

---

## Inhalt

1. [Übersicht](#übersicht)
2. [E1 — `EvaluateCommand`-Eingang](#e1--evaluatecommand-eingang)
3. [E2 — Kriterien-Scores aus Payload](#e2--kriterien-scores-aus-payload)
4. [E3 — `compute_score()` mit Gewichten](#e3--compute_score)
5. [E4 — `fail_fast` Hard-Blocks](#e4--fail_fast-hard-blocks)
6. [E5 — `append_history()` History-Persistenz](#e5--append_history)
7. [E6 — `EvalCompleted` / `EvalFailed` + Comment](#e6--evalcompleted--evalfailed)
8. [Config: `config/eval.json`](#config-configevaljson)
9. [Unterschied zu v1](#unterschied-zu-v1)

---

## Übersicht

```
 EvaluateCommand
 (criteria_scores: dict[str, float])
       │
       ▼
 ┌──────────────┐
 │ E2 Score-    │  ── cmd.payload.get("criteria_scores", {})
 │    Payload   │
 └──────┬───────┘
        │ leer?
        ├────► EvalFailed(reason="no criteria_scores") ──► Return
        │
        ▼
 ┌──────────────┐
 │ E3 compute   │  ── EvalSchema aus config/eval.json
 │    _score()  │     weight × score pro Kriterium
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ E4 fail_fast │  ── baseline + hard-block-Kriterien
 │    Gate      │
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ E5 History   │  ── data/eval_history/{issue_N}.jsonl
 │    append    │     max 90 Einträge
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ E6 Event +   │  ── EvalCompleted / EvalFailed
 │    Comment   │     scm.post_comment(N, markdown-table)
 └──────────────┘
```

---

## E1 — `EvaluateCommand`-Eingang

**Datei:** `samuel/slices/evaluation/handler.py`, `EvaluationHandler.handle`

**Woher?** Workflow-Step:
```json
{"on": "CodeGenerated", "send": "Evaluate"}
```

**Erwartete Payload:**
```python
EvaluateCommand(
    issue_number: int,
    payload={
        "criteria_scores": {
            "tests_pass": 1.0,      # 0.0 bis 1.0
            "ac_verified": 0.8,
            "no_regressions": 1.0,
            "coverage": 0.7,
        },
    },
    correlation_id: str,
)
```

**WER füllt `criteria_scores`?** Aktuell nicht sichtbar — das ist ein **Gap**.
In v1 füllte das `plugins/evaluation.py` (HTTP-Test-Runner + pytest-Fallback).
In v2 muss dieser Schritt noch verdrahtet werden (siehe "Gap" am Ende).

---

## E2 — Kriterien-Scores aus Payload

```python
criteria_scores = cmd.payload.get("criteria_scores", {})

if not criteria_scores:
    bus.publish(EvalFailed(payload={
        "issue": N, "reason": "no criteria_scores provided",
    }))
    return None
```

**Gate-Verhalten:** Ohne Scores → sofort Fail. Schützt vor "passiert nichts"-Fall wenn Caller kaputt.

---

## E3 — `compute_score()`

**Datei:** `samuel/slices/evaluation/scoring.py`

**Zweck:** Berechnet gewichteten Gesamt-Score aus allen konfigurierten Kriterien.

**Config (`config/eval.json`):**
```json
{
  "baseline": 0.6,
  "criteria": [
    {"name": "tests_pass",     "weight": 0.4, "fail_fast": true},
    {"name": "ac_verified",    "weight": 0.3, "fail_fast": false},
    {"name": "no_regressions", "weight": 0.2, "fail_fast": true},
    {"name": "coverage",       "weight": 0.1, "fail_fast": false}
  ]
}
```

**Algorithmus:**
```python
total_weight = sum(c.weight for c in config.criteria)
weighted_sum = sum(
    criteria_scores.get(c.name, 0) * c.weight
    for c in config.criteria
)
score = weighted_sum / total_weight if total_weight > 0 else 0
```

**Beispiel:**
```
criteria_scores = {
    "tests_pass": 1.0,       # weight 0.4 → 0.4
    "ac_verified": 0.8,      # weight 0.3 → 0.24
    "no_regressions": 1.0,   # weight 0.2 → 0.2
    "coverage": 0.7,         # weight 0.1 → 0.07
}
score = 0.91 (91%)
```

**Output:** `EvalResult(score, baseline, passed, fail_fast_blocked, criteria: list[CriterionResult])`

---

## E4 — `fail_fast` Hard-Blocks

Kriterien mit `fail_fast: true` müssen **unabhängig vom Gesamt-Score** passen.

**Logik:**
```python
fail_fast_blocked = [
    c.name for c in config.criteria
    if c.fail_fast and criteria_scores.get(c.name, 0) < c.threshold
]

passed = (score >= config.baseline) and not fail_fast_blocked
```

**Beispiel — Gesamt-Score hoch aber fail_fast gebrochen:**
```
tests_pass = 0.0       # fail_fast=True → BLOCK
ac_verified = 1.0      # weight 0.3 → 0.3
no_regressions = 1.0   # weight 0.2 → 0.2
coverage = 1.0         # weight 0.1 → 0.1

Gesamt-Score: (0.0×0.4 + 1.0×0.3 + 1.0×0.2 + 1.0×0.1) = 0.6 (60%)
Baseline: 0.6 — theoretisch OK
ABER: tests_pass < threshold → fail_fast_blocked=["tests_pass"]
→ passed = False
```

**Zweck:** Einzelne kritische Kriterien (Tests, Regressionen) können nicht durch andere kompensiert werden.

---

## E5 — `append_history()`

**Datei:** `samuel/slices/evaluation/scoring.py`

**Zweck:** Persistiert den Eval-Score in einer pro-Issue Historie. Zeigt Entwicklung über die Zeit.

```python
append_history(data_dir, issue_number, result, history_max=90)
```

**Pfad:** `data/eval_history/issue_{N}.jsonl` (JSONL, eine Zeile pro Eval)

**Format pro Eintrag:**
```json
{
  "timestamp": "2026-04-17T11:14:30Z",
  "score": 0.91,
  "baseline": 0.6,
  "passed": true,
  "criteria": {"tests_pass": 1.0, "ac_verified": 0.8, ...},
  "fail_fast_blocked": []
}
```

**Rotation:** Nach 90 Einträgen wird die älteste Zeile entfernt (`history_max` Config).

**Wer nutzt diese History?**
- Dashboard-Workflow-Tab (potentiell — noch nicht sichtbar in `samuel/slices/dashboard/data.py`)
- Manuelle Analyse (Score-Trend pro Issue)

---

## E6 — `EvalCompleted` / `EvalFailed` + Comment

**Bei `result.passed`:**
```python
bus.publish(EvalCompleted(payload={
    "issue": N,
    "score": result.score,
    "baseline": result.baseline,
    "criteria": {name: score for r in result.criteria},
}))
```

**Workflow-Folge:**
```json
{"on": "EvalCompleted", "send": "CreatePR"}
```
→ PR-Gates-Pipeline (`pipeline_pr_gates.md`).

**Bei NOT passed:**
```python
bus.publish(EvalFailed(payload={
    "issue": N,
    "score": ...,
    "baseline": ...,
    "fail_fast_blocked": [...],
    "criteria": {...},
}))
```

**SCM-Kommentar (immer gepostet, egal ob pass/fail):**
```markdown
## Evaluation Issue #N — PASS|FAIL

**Score:** 91.0% (Baseline: 60.0%)

**fail_fast blockiert:** tests_pass    (nur wenn relevant)

| Kriterium | Score | Gewicht |
|-----------|-------|---------|
| tests_pass | 100.0% | 40% |
| ac_verified | 80.0% | 30% |
| no_regressions | 100.0% | 20% |
| coverage | 70.0% | 10% |
```

---

## Config: `config/eval.json`

**Pydantic-Schema:** `samuel.core.config.EvalSchema`

```json
{
  "baseline": 0.6,
  "request_timeout": 10,
  "history_max": 90,
  "step_delay_seconds": 2,
  "criteria": [
    {"name": "tests_pass", "weight": 0.4, "fail_fast": true, "threshold": 0.8},
    {"name": "ac_verified", "weight": 0.3, "fail_fast": false, "threshold": 0.5},
    {"name": "no_regressions", "weight": 0.2, "fail_fast": true, "threshold": 1.0},
    {"name": "coverage", "weight": 0.1, "fail_fast": false, "threshold": 0.5}
  ]
}
```

**Sprachen:** Sprachagnostisch — Scores werden von außen (Test-Runner) geliefert.

---

## Unterschied zu v1 — und das Gap

**v1 (`plugins/evaluation.py`):**
- Misst **selbst** Scores: HTTP-Server-Tests gegen `server_url + chat_endpoint`
- Fallback: Test-Runner-Ausführung (`pytest`, `mvn test`, `npm test`, `go test`, `cargo test`)
- Auto-erkennt Sprache und führt passenden Test-Runner aus
- Parst Output → criteria_scores

**v2 (aktueller Stand):**
- **Nimmt** `criteria_scores` als Payload-Input entgegen
- Macht nur: `compute_score` + `fail_fast` + `history` + Event
- **Wer die Scores füllt, ist nicht verdrahtet**

**Ergebnis:** Die Evaluation-Pipeline ist in v2 **passiv** — sie verarbeitet nur, misst nicht.

**Gap:**
Ein Test-Runner-Adapter fehlt, der:
1. Nach `CodeGenerated` das Branch-Workspace checkout't
2. Test-Runner (sprachspezifisch) ausführt
3. Output parst → `criteria_scores` dict
4. `EvaluateCommand` mit diesem Dict sendet

**Workaround aktuell:** Manuelle `bus.send(EvaluateCommand(payload={"criteria_scores": {...}}))` oder ein vorgelagerter Handler der Test-Runs triggert.

**Offen in v1→v2 Migration.** Würde in einem separaten Issue adressiert:
- Sprachagnostisch via `config/eval.json` mit test_cmd pro Sprache (py/js/go/rs)
- Subprocess-Runner mit Timeout
- Parser für gängige Formate (pytest --tb, jest --json, go test -v)

---

## Events-Übersicht

| Event | Wann | Payload |
|---|---|---|
| `EvalFailed` | `no criteria_scores` / `not passed` | issue, reason?, score?, baseline?, fail_fast_blocked?, criteria? |
| `EvalCompleted` | `passed` | issue, score, baseline, criteria |

Alle mit `correlation_id`.

---

*Dokument erstellt: 2026-04-17, Stand Phase 14.11.*
