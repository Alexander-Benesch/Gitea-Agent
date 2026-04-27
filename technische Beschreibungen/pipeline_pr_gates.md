# Pipeline: PR-Gates (Code → PR erstellen)

Nach erfolgreicher Implementation läuft die PR-Erstellung durch 13 Gates.
Jedes Gate muss passen (wenn als `required` konfiguriert) damit der PR erstellt wird.

**Stand:** Phase 14.11.

---

## Inhalt

1. [Übersicht](#übersicht)
2. [G0 — `CreatePRCommand`-Eingang](#g0--createprcommand-eingang)
3. [G1 — `_get_branch_diff()` Git-Diff ermitteln](#g1--_get_branch_diff)
4. [G2 — `GateContext` aufbauen](#g2--gatecontext-aufbauen)
5. [G3 — Plan-Comment suchen (Kontext)](#g3--plan-comment-suchen)
6. [G4 — 13 interne Gates abarbeiten](#g4--13-interne-gates)
7. [G5 — External Gates (Plugin-Point)](#g5--external-gates)
8. [G6 — `PR` erstellen oder `GateFailed`](#g6--pr-erstellen-oder-gatefailed)
9. [Gates im Detail](#gates-im-detail)
10. [Config: `config/gates.json`](#config-configgatesjson)

---

## Übersicht

```
 CreatePRCommand
       │
       ▼
 ┌──────────────┐
 │ G1 git diff  │   subprocess "git diff --name-only base...branch"
 │    branch    │   subprocess "git diff base...branch"          (max 50 KB)
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐      comments durchsuchen
 │ G2 GateCtx   │◄───  nach "## Plan" / "Agent-Metadaten"
 │    aufbauen  │
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ G4 13 Gates  │      sorted by (isinstance(int), str(id))
 │              │      nur "required" blockieren
 └──────┬───────┘
        │  alle required passed?
        ├────► nein ────► GateFailed-Event ────► Return
        │
        ▼ ja
 ┌──────────────┐
 │ G5 External  │      IExternalGate-Plugins
 │    Gates     │
 └──────┬───────┘
        │ OK?
        ├────► nein ────► GateFailed-Event
        │
        ▼ ja
 ┌──────────────┐
 │ G6 create_pr │      scm.create_pr(head, base, title, body)
 └──────┬───────┘
        │
        ▼
    PRCreated-Event
```

---

## G0 — `CreatePRCommand`-Eingang

**Datei:** `samuel/slices/pr_gates/handler.py`

**Woher?** Workflow-Step in `config/workflows/standard.json`:
```json
{"on": "EvalCompleted", "send": "CreatePR"}
```

**Payload:**
```python
CreatePRCommand(
    issue_number: int,
    branch: str,           # z.B. "samuel/issue-136"
    base: str = "main",
    correlation_id: str,
)
```

---

## G1 — `_get_branch_diff()`

**Zweck:** Ermittelt geänderte Dateien + Diff zwischen Branch und Base via `git`.

```python
result = subprocess.run(
    ["git", "diff", "--name-only", f"{base}...{branch}"],
    capture_output=True, text=True, timeout=30,
)
changed_files = [f for f in result.stdout.strip().split("\n") if f]

result = subprocess.run(
    ["git", "diff", f"{base}...{branch}"],
    capture_output=True, text=True, timeout=30,
)
diff = result.stdout[:50000]  # Max 50KB für Gate-Checks
```

**Fehler-Fall:** Timeout/FileNotFoundError → `changed_files=[], diff=""`. Ein leerer Diff wird später von Gate 5 erkannt.

**Output:** `(changed_files: list[str], diff: str)`

---

## G2 — `GateContext` aufbauen

**Typ:** `samuel/core/types.py`
```python
@dataclass
class GateContext:
    issue_number: int
    branch: str
    changed_files: list[str]
    diff: str
    plan_comment: str | None = None
    eval_score: float | None = None
    pr_url: str | None = None
```

**Wird befüllt in:**
```python
ctx = GateContext(
    issue_number=N,
    branch=cmd.branch,
    changed_files=changed_files,
    diff=diff,
    # plan_comment + eval_score kommen später (G3, G4 Gate 4)
)
```

---

## G3 — Plan-Comment suchen

**Zweck:** Gates 2, 6, 11, 12 brauchen den Plan-Text aus dem Issue.

```python
comments = scm.get_comments(issue_number)
for c in reversed(comments):   # neueste zuerst
    if "## Plan" in c.body or "Agent-Metadaten" in c.body:
        ctx = GateContext(..., plan_comment=c.body)
        break
```

**Reverse-Iteration:** Nimmt neuesten Plan (falls Retry-Run mehrere Plans gepostet hat).

---

## G4 — 13 interne Gates

**Registry:** `samuel/slices/pr_gates/gates.py` → `GATE_REGISTRY: dict[int | str, Callable]`

```python
GATE_REGISTRY = {
    1:    gate_1_branch_guard,
    2:    gate_2_plan_comment,
    3:    gate_3_metadata_block,
    4:    gate_4_eval_timestamp,
    5:    gate_5_diff_not_empty,
    6:    gate_6_self_consistency,
    7:    gate_7_scope_guard,
    8:    gate_8_slice_gate,
    9:    gate_9_quality_pipeline,
    10:   gate_10_eval_score,
    11:   gate_11_ac_verification,
    12:   gate_12_ready_to_close,
    "13a": gate_13a_branch_freshness,
    "13b": gate_13b_destructive_diff,
}
```

**Jedes Gate:**
```python
def gate_N_name(ctx: GateContext) -> GateResult:
    # berechnet passed: bool, reason: str, ggf. owasp_risk: str
    return GateResult(gate=N, passed=..., reason=..., owasp_risk=...)
```

**Ablauf:**
```python
all_gate_ids = set(config.required) | set(config.optional)
active = all_gate_ids - set(config.disabled)

for gate_id in sorted(active, key=lambda x: (isinstance(x, str), str(x))):
    gate_fn = GATE_REGISTRY.get(gate_id)
    if not gate_fn: continue
    result = gate_fn(ctx)
    results.append(result)
    if not result.passed and gate_id in config.required:
        blocked = True
        bus.publish(GateFailedEvent(payload={
            "issue": N, "gate": gate_id,
            "reason": result.reason, "owasp_risk": result.owasp_risk,
        }))
```

**Sort-Regel:** Ints vor Strings → 1, 2, ..., 12, "13a", "13b".

---

## G5 — External Gates

**Port:** `samuel/core/ports.py` → `IExternalGate`
```python
class IExternalGate(ABC):
    name: str
    @abstractmethod
    def run(self, context: GateContext) -> GateResult: ...
```

**Plugin-Point:** Konstruktor nimmt `external_gates: list[IExternalGate]` entgegen. Werden nach den 13 internen Gates ausgeführt.

**Beispiel-Use-Case:** CVE-Scanner, Lizenz-Checker, externe Security-Services.

**Fehler-Handling:** Einzelner Exception von `ext.run()` wird abgefangen → `GateFailedEvent` mit `external=True, reason="External gate error: {exc}"`.

---

## G6 — `PR` erstellen oder `GateFailed`

**Wenn `blocked`:**
```python
return {
    "passed": False,
    "results": results,         # alle GateResults
    "blocked_gates": [r for r in results if not r.passed],
}
# Kein PR wird erstellt. GateFailed-Events wurden bereits publiziert.
```

**Wenn alle required + external OK:**
```python
attribution = ai_attribution_fn() if ai_attribution_fn else None
# z.B. "AI-Generated-By: S.A.M.U.E.L.@v2" (aus samuel/slices/privacy/ai_act.py)

title = f"feat: Issue #{N}"
body_parts = [f"## Issue #{N}"]
if attribution:
    body_parts.append(f"\n{attribution}")

pr = scm.create_pr(
    head=cmd.branch, base=cmd.base or "main",
    title=title, body="\n".join(body_parts),
)

bus.publish(PRCreated(payload={
    "issue": N, "branch": cmd.branch,
    "pr_number": pr.number, "pr_url": pr.html_url,
    "ai_attribution": attribution,
}))
```

---

## Gates im Detail

### Gate 1 — Branch-Guard
- Fail: Branch ist `main`/`master`/leer → OWASP `A05:2021`
- Grund: Verhindert PR von Main auf Main

### Gate 2 — Plan-Comment vorhanden
- Fail: Kein `ctx.plan_comment` oder <20 chars
- Grund: Ohne Plan kein Trace der LLM-Absicht

### Gate 3 — Agent-Metadaten-Block
- Fail: "Agent-Metadaten" nicht im Plan-Comment
- Grund: v1-Feature für Reproduzierbarkeit (model, tokens, correlation)

### Gate 4 — Eval-Score-Timestamp
- Fail: `ctx.eval_score is None`
- Grund: Evaluation muss vor PR gelaufen sein

### Gate 5 — Diff nicht leer
- Fail: `ctx.diff` leer
- Grund: Leerer Diff = nichts zu mergen

### Gate 6 — Plan-Diff-Konsistenz
- Fail: >50% der im Plan referenzierten Dateien nicht im Diff
- Grund: LLM hat was anderes gemacht als im Plan stand

### Gate 7 — Scope-Guard
- Fail: Geänderte Datei enthält `.env`, `secrets`, `credentials` → OWASP `A01:2021`
- Grund: Kein PR mit geheimen Daten

### Gate 8 — Slice-Gate (Cross-Slice-Import)
- Fail: Neuer Import `from samuel.slices.A` in Datei von Slice `B` → OWASP `A05:2021`
- Grund: v2-Architektur-Regel

### Gate 9 — Quality-Pipeline (Python-Syntax)
- Fail: Python-AST-Parse der geänderten `.py`-Files schlägt fehl
- Grund: Kein PR mit Syntax-Fehlern

### Gate 10 — Eval-Score-Threshold
- Fail: `eval_score < 0.6`
- Grund: Baseline-Qualität muss erreicht sein

### Gate 11 — AC-Verifikation
- Fail: Keine `- [ ]` oder `- [x]` im Plan
- Grund: Ohne ACs keine Prüfkriterien

### Gate 12 — Ready-to-Close
- Fail: `- [ ]` (unchecked) > 0 im Plan
- Grund: Alle ACs müssen abgehakt sein

### Gate 13a — Branch-Freshness
- Fail: Branch >50 Commits hinter main → OWASP `A05:2021`
- Grund: Veralteter Branch verursacht Merge-Konflikte

### Gate 13b — Destruktiver Diff
- Fail: `deleted_lines > added_lines * 3` UND `deleted_lines > 50` → OWASP `A05:2021`
- Grund: Massiv mehr Löschungen als Hinzufügungen = verdächtig

---

## Config: `config/gates.json`

```json
{
  "required": [1, 2, 5, 7, 8, 9],
  "optional": [3, 4, 6, 10, 11, 12, "13a", "13b"],
  "disabled": []
}
```

**Semantik:**
- `required`: muss passen, sonst Block
- `optional`: wird ausgeführt, fail wird geloggt aber blockiert nicht
- `disabled`: wird gar nicht ausgeführt

**Laden:** `samuel.core.config.load_gates_config()` — Pydantic-validiert via `GatesConfigSchema`.

---

*Dokument erstellt: 2026-04-17, Stand Phase 14.11.*
