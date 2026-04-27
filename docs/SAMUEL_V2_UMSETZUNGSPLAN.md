Der Plan umfasst 10 Phasen plus parallele Tracks. Hier die wichtigsten Designentscheidungen die ich getroffen habe:
Reihenfolge ist nicht zufällig. Phase 0a muss vor allem kommen weil sonst der Pre-commit Hook jeden Commit in die neue Struktur blockiert. Phase 0b (Kernel) muss vor Phase 1 kommen weil die Bridge AuditEvent aus dem Kernel braucht. Phasen 1–3 können parallel laufen, sind aber alle Voraussetzung für Phase 4.
Skeleton-Abstraktion als Parallel-Track. Das ist der tiefste Bruchpunkt — 5 Systeme hängen daran. Ich habe es als eigenständigen Track (SP) modelliert der spätestens vor Phase 4 fertig sein muss, weil der Planning-Slice Skeleton-Context braucht.
Semaphore-Release ist in Phase 5 explizit eingebaut, nicht als Nachgedanke. Die Terminal-Event-Liste (PRCreated, WorkflowBlocked, LLMUnavailable, PlanBlocked, WorkflowAborted) muss vollständig sein — ein fehlendes Event würde den Watch-Handler dauerhaft stallen.
Jede Phase hat ein Definition of Done das messbar ist — kein vages "fertig", sondern konkrete CLI-Befehle und Test-Aussagen die grün sein müssen.




# S.A.M.U.E.L. v2 — Umsetzungsplan

> Basiert auf: SAMUEL_ARCHITECTURE_V2.md  
> Prinzip: **Kein Big-Bang. Kein Downtime. Jeder Schritt einzeln testbar.**  
> Der Agent läuft während der gesamten Migration durch. Sicherheitsgates werden nie degradiert.

---

## Grundregeln für die gesamte Migration

1. **Bridge-first:** Kein v1-Modul wird gelöscht bevor sein v2-Ersatz vollständig getestet ist.
2. **Tests immer grün:** Jeder Commit auf `main` muss alle bestehenden Tests bestehen.
3. **Security-Gates unveränderlich:** Die 14 PR-Gates, der Pre-commit Hook und die Startup-Validierung dürfen zu keinem Zeitpunkt abgeschwächt werden.
4. **Self-Mode Parität:** Jede Änderung die den Agent-Code betrifft wird über `--self` eingespielt — mit denselben Gates wie jedes andere Projekt.
5. **Architecture-Tests als Blocker:** `test_architecture_v2.py` läuft als Pre-commit Check ab Phase 0.

---

## Übersicht: Phasen und Abhängigkeiten

```
Vorarbeiten (P0a) ──► Shared Kernel (P0b) ──► Audit-Bridge (P1)
                                                     │
                              ┌──────────────────────┤
                              ▼                      ▼
                        SCM-Port (P2)          LLM-Port (P3)
                              │                      │
                              └──────────┬───────────┘
                                         ▼
                                  Planning-Slice (P4)
                                         │
                              ┌──────────┼──────────┐
                              ▼          ▼           ▼
                        Impl. (P5)  PR-Gates (P6)  Eval (P7)
                              │          │           │
                              └──────────┴─────┬─────┘
                                               ▼
                                     Watch+Heal+Dashboard (P8)
                                               │
                                               ▼
                                          Aufräumen (P9)
                                               │
                                               ▼
                                    Server-Hook + Flexibilität (P10)

Parallel zu allem: Skeleton-Abstraktion (SP) — muss vor P4 abgeschlossen sein
```

---

## Phase 0a — Vorarbeiten (Blocker VOR erstem Slice-Commit)

**Ziel:** Die drei Blocker beseitigen die jeden Commit in die neue Struktur verhindern würden.  
**Dauer:** Klein — reine Code-Anpassungen, kein Neubau.  
**Abhängigkeit:** Keine.

### Aufgabe 0a.1 — Pre-commit Hook: Test-Konvention für beide Welten

**Was:** Der Hook sucht für `commands/plan.py` die Datei `tests/test_plan.py`. In v2 wäre das `samuel/slices/planning/handler.py` — der Hook würde `test_handler.py` suchen (zu generisch, kollidiert). Der Hook muss beide Konventionen gleichzeitig unterstützen.

**Konkret:**
- Hook-Logik erweitern: für Dateien unter `samuel/slices/<slice>/` suche `samuel/slices/<slice>/tests/test_<stem>.py` (Option B aus Architektur)
- Fallback bleibt: für alle anderen Dateien gilt die alte Konvention `tests/test_<stem>.py`
- Beide Pfade müssen im Hook konfigurierbar sein (via `config/hooks.json` — Sektion 15.8)

**Akzeptanzkriterien:**
- `git commit` auf einer neuen v2-Slice-Datei findet den Test im Slice-Ordner
- `git commit` auf bestehenden v1-Dateien findet weiter den Test im `tests/`-Ordner
- Kein bestehender Test schlägt fehl

---

### Aufgabe 0a.2 — helpers.py: Auflösung nach Entscheidungsmatrix

**Was:** `helpers.py` (488 Zeilen, 23 Funktionen) muss aufgelöst werden bevor Slices entstehen. Sonst importiert jeder Slice `helpers.py` direkt — das verletzt die Kernel-Regel.

**Konkret** (Entscheidungsmatrix vollständig abarbeiten):

| Funktion | Ziel | Kommentar |
|----------|------|-----------|
| `AgentAbort` | `core/errors.py` | Mit Event-Publishing (siehe 0a.3) |
| `git_run`, `git_output` | `core/types.py` | Shell-Helper, überall gebraucht |
| `_get_project` | `core/config.py` | PROJECT_ROOT-Zugriff |
| `_get_gitea` | wird SCM-Port-Injection | Entfernt in Phase 2 |
| `strip_html`, `_S` | `core/types.py` | 15+ Caller |
| `validate_comment` | `core/types.py` | pr.py, implement.py |
| `get_user_feedback_comments` | `slices/planning/` | plan.py, watch.py |
| `has_detailed_plan` | `slices/planning/` | implement.py |
| `build_metadata` | `slices/pr_gates/` | pr.py |
| `format_history_block` | `slices/pr_gates/` | pr.py |
| `dashboard_event` | `slices/dashboard/` | nur dashboard |
| `log_agent_event` | → Audit-Event auf Bus | Bridge-Phase |
| `current_issue_from_branch` | `slices/watch/` | 1 Caller |
| `estimate_slice_tokens` | `slices/context/` | implement_llm |
| `_get_slice_hmac_key` | `slices/security/` | Slice-Gate |
| `_sign_slice_entry` | `slices/security/` | get_slice, chat_workflow |
| `verify_slice_signature` | `slices/security/` | pre-commit hook |
| `log_slice_request` | `slices/context/` | get_slice |
| `safe_int`, `safe_float` | `core/types.py` | pr.py, dashboard |

**Vorgehen:** Jede Funktion in eine neue Heimat verschieben, alle Importe aktualisieren, Tests laufen lassen. Nicht alles auf einmal — eine Funktion nach der anderen, je ein Commit.

**Akzeptanzkriterien:**
- `helpers.py` existiert nicht mehr oder ist leer
- Alle Tests grün
- `grep -r "from helpers import\|import helpers" .` ergibt keine Treffer außer Tests

---

### Aufgabe 0a.3 — AgentAbort: Event-Publishing hinzufügen

**Was:** `AgentAbort` raised und in `cmd_auto` gefangen — impliziter Vertrag. In v2 muss jeder Abort auch ein Audit-Event produzieren, auch wenn es außerhalb von `cmd_auto` geraised wird.

**Konkret:**
```python
# samuel/core/errors.py
class AgentAbort(Exception):
    def __init__(self, message, gate=None, issue=None):
        super().__init__(message)
        if _bus_available():
            bus.publish(WorkflowAborted(reason=message, gate=gate, issue=issue))
```

**Akzeptanzkriterien:**
- Jedes `AgentAbort` produziert ein `WorkflowAborted`-Event im Audit-Log
- Bestehende `except AgentAbort`-Handler funktionieren unverändert

---

### Aufgabe 0a.4 — _cfg(): Bridge implementieren

**Was:** Hunderte `_cfg("KEY")` Aufrufe importieren direkt `settings.py`. In v2 muss Config über `IConfig`-Port kommen. Bridge erlaubt Parallelbetrieb.

**Konkret:**
```python
# settings.py — _cfg() wird zur Bridge
def _cfg(key, default=None):
    if _bus and _bus.has_port(IConfig):
        return _bus.get_port(IConfig).get(key, default)
    return _legacy_cfg(key, default)
```

**Akzeptanzkriterien:**
- Alle bestehenden `_cfg()`-Aufrufe funktionieren weiterhin
- Neue Slices bekommen Config per Constructor-Injection statt `_cfg()`
- Architecture-Test `test_no_module_level_config` läuft ohne Fehler für alle neuen Slice-Dateien

---

### Aufgabe 0a.5 — Sequence-Validator auf warn-only verifizieren

**Was:** Der Validator lernt v1-Patterns. v2-Code (`bus.publish(...)` statt `gitea_api.get_issue()`) kennt er nicht — würde False Positives produzieren.

**Konkret:**
- In `config/agent.json` verifizieren: `"sequence_validator": "warn"` (nicht `"block"`)
- Darf während der gesamten Migration nicht auf `"block"` gesetzt werden
- Nach jeder abgeschlossenen Phase: `repo_patterns.json` neu lernen

**Akzeptanzkriterien:**
- Agent läuft durch ohne Sequence-Validator-Block bei neuem v2-Code
- Warnungen werden ins Audit-Log geschrieben (auditierbar, nicht blockierend)

---

### Definition of Done — Phase 0a

- [ ] Hook unterstützt beide Test-Konventionen
- [ ] `helpers.py` vollständig aufgelöst, alle Importe aktualisiert
- [ ] `AgentAbort` produziert Audit-Events
- [ ] `_cfg()` Bridge aktiv
- [ ] Sequence-Validator auf warn-only bestätigt
- [ ] Alle bestehenden Tests grün
- [ ] `python3 agent_start.py --self --doctor` meldet keinen neuen Fehler

---

## Phase 0b — Shared Kernel bauen

**Ziel:** Den neuen Code-Kern erstellen auf dem alle Slices aufbauen.  
**Abhängigkeit:** Phase 0a abgeschlossen.  
**Besonderheit:** Rein neuer Code — bricht nichts, kann parallel zur laufenden v1 existieren.

### Aufgabe 0b.1 — samuel/core/ anlegen

Verzeichnis `samuel/core/` anlegen mit folgenden Dateien in dieser Reihenfolge:

**Reihenfolge ist wichtig** (zirkuläre Importe vermeiden):

1. `errors.py` — `AgentAbort`, `SecurityViolation`, `GateFailed`, `ProviderUnavailable` (keine Abhängigkeiten)
2. `types.py` — `LLMResponse`, `GateContext`, `GateResult`, `AuditQuery`, `SkeletonEntry`, `safe_int`, `safe_float`, `strip_html`, `validate_comment` (nur stdlib)
3. `ports.py` — alle `IXxx` ABCs (importiert nur `types.py` und `errors.py`)
4. `events.py` — alle Event-Typen als Dataclasses mit `event_version`, `correlation_id`, `causation_id` (importiert nur `types.py`)
5. `commands.py` — alle Command-Typen mit `idempotency_key` (importiert nur `types.py`)
6. `config.py` — `IConfig`-Implementierung + Pydantic-Schemas für alle Config-Dateien
7. `logging.py` — Logging-Setup
8. `bus.py` — Bus + alle Middlewares (`IdempotencyMiddleware`, `SecurityMiddleware`, `PromptGuardMiddleware`, `AuditMiddleware`, `ErrorMiddleware`, `MetricsMiddleware`)
9. `workflow.py` — `WorkflowEngine` mit `has_handler()`-Check + `UnhandledCommand`-Event
10. `bootstrap.py` — vollständige Startup-Sequenz (Sektion 4.3 der Architektur)

### Aufgabe 0b.2 — Architecture-Tests schreiben

`tests/test_architecture_v2.py` anlegen mit allen Tests aus Sektion 12.2:
- `test_no_cross_slice_imports()`
- `test_no_direct_adapter_usage()`
- `test_shared_kernel_minimal()` — inkl. `workflow` und `bootstrap` in `allowed`
- `test_every_v1_file_mapped()`
- `test_event_types_complete()`
- `test_all_gates_have_owasp()`
- `test_no_module_level_config()` (neu — prüft Slices)

Diese Tests als Pre-commit Check einbinden: nach dem ersten Commit in `samuel/core/` läuft `test_architecture_v2.py` bei jedem Commit.

### Aufgabe 0b.3 — Skeleton-Abstraktion (Parallel-Track SP)

**Wichtig:** Muss vor Phase 4 (Planning-Slice) abgeschlossen sein, weil der Planning-Slice den Skeleton-Context nutzt.

- `ISkeletonBuilder` ABC in `core/ports.py` definiert (bereits in 0b.1 enthalten)
- `SkeletonEntry` Dataclass in `core/types.py` (bereits in 0b.1 enthalten)  
- `PythonASTBuilder` als erste Implementierung extrahieren (aus bestehendem `context_loader.py`)
- Skeleton-Format bleibt identisch — nur neues `language`-Feld ergänzen
- Registry-Mechanismus: `SKELETON_BUILDERS: dict[str, ISkeletonBuilder]`
- Bestehende Skeleton-Generierung auf neue Abstraktion umstellen
- Alle 5 abhängigen Systeme (Hallucination-Guard, Scope-Guard, Pre-Implementation Check, Slice-Gate, Context-Loading) weiterhin funktionsfähig

**Akzeptanzkriterien:**
- `python3 agent_start.py --self --build-skeleton` erzeugt identisches `repo_skeleton.json` wie vorher
- Alle Skeleton-abhängigen Tests grün

### Definition of Done — Phase 0b

- [ ] `samuel/core/` mit allen 10 Dateien angelegt
- [ ] Alle Typen vollständig definiert (`LLMResponse`, `GateContext`, `GateResult`, `SkeletonEntry`, `AuditQuery`)
- [ ] Bus läuft, Middleware-Kette funktioniert (Unit-Tests)
- [ ] Alle 6 Middleware-Klassen implementiert und getestet
- [ ] WorkflowEngine mit `UnhandledCommand`-Event bei fehlendem Handler
- [ ] Bootstrap-Sequenz vollständig (alle 12 Schritte aus Sektion 4.3)
- [ ] Architecture-Tests angelegt und grün
- [ ] Skeleton-Abstraktion abgeschlossen (`ISkeletonBuilder`, `PythonASTBuilder`)
- [ ] `python3 agent_start.py --self --doctor` meldet keinen neuen Fehler

---

## Phase 1 — Audit-Migration (erste Bridge)

**Ziel:** `plugins/audit.py` (639 Zeilen, 15+ direkte Importstellen) auf den Bus migrieren. Das ist der größte Querverknüpfungspunkt — wenn der Bus läuft, ist der Dominoeffekt am größten.  
**Abhängigkeit:** Phase 0b abgeschlossen.

### Aufgabe 1.1 — Audit-Bridge in plugins/audit.py

```python
def log(evt, cat, msg, *, lvl="info", issue=0, **kwargs):
    if _bus_available():
        event = AuditEvent(
            name=evt, cat=cat, msg=msg, lvl=lvl,
            correlation_id=_current_correlation_id(),
            **kwargs
        )
        bus.publish(event)
        return event.id
    return _write_jsonl(evt, cat, msg, lvl=lvl, issue=issue, **kwargs)
```

Keine der 15+ Aufrufstellen muss geändert werden. `correlation_id` kommt aus dem Bus-Kontext.

### Aufgabe 1.2 — Audit-Slice anlegen

`samuel/slices/audit_trail/` mit:
- `handler.py` — subscribed auf ALLE Events, schreibt via `IAuditSink`
- `owasp.py` — OWASP-Mapping + Klassifikation (aus bestehendem Code)
- `tests/`

### Aufgabe 1.3 — JSONL-Adapter anlegen

`samuel/adapters/audit/jsonl.py` — implementiert `IAuditSink`, synchron (kein Buffer nötig).

`samuel/adapters/audit/upcasters.py` — Upcaster-Tabelle für historische Events (Event-Schema-Versionierung).

### Aufgabe 1.4 — AsyncAuditSink implementieren

Für externe Sinks (Webhook, Elasticsearch). Buffer-Size konfigurierbar. Security-Events (`owasp_risk` gesetzt oder `lvl == "error"`) werden bei vollem Buffer synchron auf JSONL-Fallback geschrieben, nie verworfen.

### Aufgabe 1.5 — config/audit.json Schema

Pydantic-Schema anlegen. Validierung beim Start via `StartupValidationCommand`.

**Akzeptanzkriterien Phase 1:**
- Alle bisherigen Audit-Events landen weiterhin im JSONL
- `correlation_id` in jedem neuen Event gesetzt
- `--doctor` meldet keine Audit-Inkonsistenzen
- Upcaster liest alte Events ohne Fehler

---

## Phase 2 — SCM-Port (Gitea → IVersionControl)

**Ziel:** `gitea_api.py` hinter den `IVersionControl`-Port abstrahieren. Nach dieser Phase ist GitHub-Support möglich ohne Slice-Änderungen.  
**Abhängigkeit:** Phase 0b abgeschlossen (Port-Interface existiert).

### Aufgabe 2.1 — IVersionControl vollständig definieren

In `core/ports.py` (aus 0b.1 bereits als Skeleton vorhanden):
- Alle Kern-Methoden: `get_issue`, `get_comments`, `post_comment`, `create_pr`, `swap_label`, `list_issues`
- URL-Generierung: `issue_url`, `pr_url`, `branch_url`
- Capabilities-Property

### Aufgabe 2.2 — GiteaAdapter anlegen

`samuel/adapters/gitea/adapter.py` + `api.py`:
- Wraps bestehende `gitea_api.py`-Funktionen
- Implementiert `IVersionControl` vollständig
- Capabilities: `{"labels", "webhooks_basic"}`

### Aufgabe 2.3 — gitea_api.py zur Bridge machen

```python
# gitea_api.py — Bridge
_adapter: GiteaAdapter | None = None

def get_issue(number):
    if _adapter:
        return _adapter.get_issue(number)
    return _legacy_get_issue(number)
```

Alle 20+ direkten Importstellen funktionieren weiterhin ohne Änderung.

### Aufgabe 2.4 — IAuthProvider implementieren

`samuel/adapters/auth/static_token.py` — Gitea-Bot-Token.  
Interface vorbereitet für `GitHubAppAuth` (noch nicht implementieren).

### Aufgabe 2.5 — Provider-agnostische Config

`.env`-Migration vorbereiten:
- Bootstrap erkennt beide Formate (`GITEA_URL` Legacy + `SCM_PROVIDER` neu)
- Setup-Wizard empfiehlt neues Format
- Dokumentation: Migration-Guide für bestehende Installationen

**Akzeptanzkriterien Phase 2:**
- `--doctor` meldet keine SCM-Fehler
- Alle bestehenden Workflows laufen durch
- `GiteaAdapter`-Unit-Tests: alle Methoden gegen Mock-API getestet
- `test_no_direct_adapter_usage()` grün (noch keine Slices, daher trivial — aber Baseline setzen)

---

## Phase 3 — LLM-Port

**Ziel:** LLM-Aufrufe aus `implement_llm.py`, `plan.py`, `review.py`, `heal.py` hinter `ILLMProvider` abstrahieren.  
**Abhängigkeit:** Phase 0b abgeschlossen.

### Aufgabe 3.1 — ILLMProvider vollständig definieren

In `core/ports.py`:
- `complete(messages: list[dict], **kwargs) -> LLMResponse`
- `estimate_tokens(text: str) -> int`
- `context_window: int` (Pflicht-Property)
- `capabilities: set[str]` (Optional)

### Aufgabe 3.2 — LLMResponse sicherstellen

Dataclass in `core/types.py` (bereits in 0b.1 definiert):
`text`, `input_tokens`, `output_tokens`, `cached_tokens`, `stop_reason`, `model_used`, `latency_ms`.

### Aufgabe 3.3 — Adapter anlegen

- `samuel/adapters/llm/claude.py` — Claude/Anthropic
- `samuel/adapters/llm/deepseek.py`
- `samuel/adapters/llm/ollama.py`
- `samuel/adapters/llm/lmstudio.py`
- `samuel/adapters/llm/costs.py` — Kostenberechnung (OpenRouter + Fallback-Tabelle)

Jeder Adapter gibt `LLMResponse` zurück. Kosten werden aus `response.cached_tokens` korrekt berechnet.

### Aufgabe 3.4 — CircuitBreakerAdapter

`samuel/adapters/llm/circuit_breaker.py`:
- Zustände: `closed → open → half-open`
- `FAILURE_THRESHOLD = 3`, `COOLDOWN_SECONDS = 120`
- Wraps jeden LLM-Adapter transparent
- Publiziert `ProviderCircuitOpen`-Event wenn Provider als ausgefallen markiert wird

### Aufgabe 3.5 — SanitizingLLMAdapter

`samuel/adapters/llm/sanitizer.py`:
- `response.text = strip_html(response.text)` (Feld ist `.text`, nicht `.content`)
- `response.text = truncate_if_excessive(response.text)`
- Defense in Depth: zweite Sanitization-Schicht vor dem Quality-Slice

### Aufgabe 3.6 — plugins/llm.py zur Bridge machen

Bestehende LLM-Aufrufe delegieren intern an den neuen Adapter. Signatur unverändert.

**Akzeptanzkriterien Phase 3:**
- Alle LLM-Adapter liefern `LLMResponse` mit vollständigen Metadaten
- Circuit Breaker: nach 3 Fehlern öffnet der Breaker, nach 120s Cooldown schließt er (Unit-Test)
- `SanitizingLLMAdapter`: `.text`-Feld wird korrekt bereinigt (kein AttributeError)
- Token-Kosten aus `response.cached_tokens` korrekt berechnet (Unit-Test mit Mock-Response)

---

## Phase 4 — Erster Slice: Planning

**Ziel:** `commands/plan.py` als vollständigen Slice extrahieren. Proof of Concept für die Slice-Architektur.  
**Abhängigkeit:** Phasen 1, 2, 3 abgeschlossen. Skeleton-Abstraktion (SP) abgeschlossen.  
**Warum zuerst:** Kleinster Slice, klar abgegrenzt, gut testbar.

### Aufgabe 4.1 — samuel/slices/planning/ anlegen

```
samuel/slices/planning/
  handler.py      PlanIssueCommand → Context aufbauen → LLM → Validierung → PlanCreated
  events.py       PlanCreated, PlanValidated, PlanBlocked, PlanRetry, PlanPosted,
                  PlanApproved, PlanFeedbackReceived, PlanRevised
  tests/
    test_handler.py
```

### Aufgabe 4.2 — PlanIssueCommand definieren

In `core/commands.py`. Felder: `issue_number`, `correlation_id`, `idempotency_key`.

### Aufgabe 4.3 — 3-Stufen LLM-Qualitätskontrolle

Im Handler:
1. `PromptGuardMiddleware` — Pflichtmarker + XML-Delimiter für Issue-Inhalt
2. Quality-Slice (PlanValidationCommand) — 7 objektive Checks, Score-Schwellen
3. Pre-Implementation Check (tokenfrei) — Plan gegen aktuelles Skeleton

### Aufgabe 4.4 — commands/plan.py zur Bridge machen

```python
# commands/plan.py — Bridge
def cmd_plan(issue_number, **kwargs):
    if _bus_available():
        return bus.send(PlanIssueCommand(issue_number=issue_number,
                                        idempotency_key=f"plan:{issue_number}"))
    return _legacy_cmd_plan(issue_number, **kwargs)
```

### Aufgabe 4.5 — Integration-Test: Vollständiger Plan-Durchlauf

Test-Szenario: `PlanIssueCommand` rein → Events prüfen:
- `PlanCreated` Event wird publiziert
- `PlanValidated` oder `PlanBlocked` je nach Score
- Audit-Log enthält alle Events mit `correlation_id`
- Bei Score < 50%: kein Post auf SCM, `PlanBlocked` Event

**Akzeptanzkriterien Phase 4:**
- `test_no_cross_slice_imports()` grün
- `test_no_direct_adapter_usage()` grün für Planning-Slice
- Vollständiger Plan-Durchlauf im Integration-Test mit Mock-SCM und Mock-LLM
- Bestehende `--issue`-Funktionalität weiterhin lauffähig (Bridge aktiv)

---

## Phase 5 — Implementation-Slice

**Abhängigkeit:** Phase 4 abgeschlossen.

### Aufgaben

**5.1** `samuel/slices/implementation/` anlegen:
```
handler.py       ImplementCommand → Branch → Context → LLM-Loop → Patches → Quality
llm_loop.py      Slice-Request-Loop (max 5 Runden), Patch-Retry
patch_parser.py  REPLACE LINES + SEARCH/REPLACE Parser (aus plugins/patch.py)
events.py        CodeGenerated, ImplementRetryCommand, WorkflowBlocked, TokenLimitHit
tests/
```

**5.2** `IPatchApplier`-Registry in `core/ports.py`:
- `LinePatchApplier` (`.py`, Default)
- `JSONPatchApplier` (`.json` — validiert Struktur nach Patch)
- `YAMLPatchApplier` (`.yaml`)
- Fallback: `LinePatchApplier` für unbekannte Endungen

**5.3** Resume-Mechanik ausbauen (Sektion 15.10):
- `WorkflowCheckpoint` Dataclass mit `phase`, `step`, `correlation_id`
- Checkpoints an allen kritischen Übergängen: nach Patch-Apply, nach Quality-Check
- `has_pending_checkpoint()` beim Start → automatisches Resume

**5.4** Semaphore-Release-Verdrahtung:
- Bootstrap subscribed auf Terminal-Events: `PRCreated`, `WorkflowBlocked`, `LLMUnavailable`, `PlanBlocked`, `WorkflowAborted`
- Jedes Terminal-Event → `watch_handler.release_slot()`

**5.5** `commands/implement_llm.py` zur Bridge machen.

**Akzeptanzkriterien Phase 5:**
- End-to-End Test: `ImplementCommand` → `CodeGenerated` mit Mock-LLM
- `JSONPatchApplier` lehnt invalides JSON nach Patch ab
- Resume: nach simuliertem Absturz beim 2. Patch startet der Slice am Checkpoint fort
- Token-Limit-Szenario: unvollständige Patches werden zurückgerollt

---

## Phase 6 — PR-Gates-Slice

**Abhängigkeit:** Phasen 4 und 5 abgeschlossen.

### Aufgaben

**6.1** `samuel/slices/pr_gates/` anlegen:
```
handler.py    PRGatesHandler — CreatePRCommand → alle Gates → PRCreated/GateFailed
gates.py      Individuelle Gate-Checks (1–14)
events.py     PRCreated, GateFailed, GateWarning
tests/
```

**6.2** `PRGatesHandler` mit Bus-Injection (kein globales `bus`):
```python
class PRGatesHandler:
    def __init__(self, bus: Bus, config: IConfig, scm: IVersionControl):
        self._bus = bus
        self._gates = self._load_gates(config)
```

**6.3** `config/gates.json` implementieren:
- `required`, `optional`, `disabled`, `custom`-Felder
- Fehlende Datei → alle 14 Gates als `required` (v1-Kompatibilität)
- Custom Gates via `IExternalGate` (Sektion 16.1)

**6.4** `IExternalGate`-Infrastruktur:
- Bootstrap lädt `config/integrations.json`
- Externe Gates werden nach den internen Gates ausgeführt
- Timeout pro External Gate konfigurierbar (default 30s)
- `on_failure: "block"` oder `"warn"`

**6.5** `commands/pr.py` zur Bridge machen.

**Akzeptanzkriterien Phase 6:**
- Alle 14 Gates einzeln unit-getestet (Pass + Fail-Szenario)
- `config/gates.json` mit `disabled: [6]` überspringt Gate 6 (Self-Check) für Nicht-SAMUEL-Projekte
- External Gate per Webhook: Mock-Server antwortet mit `{"passed": false}` → PR blockiert
- Bestehende `--pr`-Funktionalität läuft durch

---

## Phase 7 — Evaluation-Slice

**Abhängigkeit:** Phase 4 abgeschlossen.

### Aufgaben

**7.1** `samuel/slices/evaluation/` anlegen:
```
handler.py    EvaluateCommand → Score-Pipeline → EvalCompleted/EvalFailed
scoring.py    Baseline, Score-History, gewichtetes Multi-Kriterien (config/eval.json)
tests/
```

**7.2** `config/eval.json` Schema + Pydantic-Validierung:
- `weights` pro Kriterium
- `baseline` (Default 0.8)
- `fail_fast_on` (blockiert unabhängig vom Gesamtscore)
- Dashboard zeigt Einzelscores statt nur Aggregat

**7.3** `commands/eval_after_restart.py` zur Bridge machen.

**Akzeptanzkriterien Phase 7:**
- Eval mit Syntax-Fehler: `fail_fast_on: ["syntax_valid"]` blockiert trotz 90% Gesamtscore
- Score-History wird korrekt fortgeschrieben
- Gate 4 (Eval-Timestamp) und Gate 10 (Eval-Score) nutzen den neuen Slice

---

## Phase 8 — Watch, Healing, Dashboard, alle übrigen Slices

**Abhängigkeit:** Phasen 4–7 abgeschlossen.

### 8.1 Watch-Slice

`samuel/slices/watch/`:
- `WatchHandler` mit Semaphore-Bounded Concurrency
- `LabelConsistencyCheck` am Anfang jedes Zyklus
- Hot-Reload: `ReloadConfigCommand` am Zyklusbeginn
- Dual-Mode: Polling (Default) oder Webhook-first (wenn `scm.ingress == "webhook"`)

### 8.2 Healing-Slice

`samuel/slices/healing/`:
- `HealCommand` mit generischem `failure_type`: `"eval"`, `"lint"`, `"typecheck"`, `"test"`, `"dependency"`
- Subscribed auf: `EvalFailed`, `LintFailed`, `TypeCheckFailed` (feature-flag-abhängig)

### 8.3 Dashboard-Slice

`samuel/slices/dashboard/`:
- Alle 6 Tabs weiterhin funktionsfähig
- Dashboard-URLs via `scm.issue_url()` / `scm.pr_url()` (provider-agnostisch)
- CSRF-Schutz im Standalone-Modus (Pflicht wenn öffentlich erreichbar)
- `INotificationSink`-Adapter: Slack, Teams, GenericWebhook (via `config/notifications.json`)
- `/api/metrics`-Endpoint: `MetricsMiddleware.get_stats()` als JSON

### 8.4 Alle weiteren Slices

In dieser Reihenfolge (von einfach nach komplex):
1. `changelog/` — `ChangelogCommand`
2. `review/` — `ReviewCommand`
3. `session/` — Session-Limits, Token-Budget, `WorkflowCheckpoint`-Persistenz
4. `health/` — `HealthCheckCommand`, Startup-Validierung, Self-Check
5. `setup/` — Setup-Wizard, Service-Installation
6. `code_analysis/` — CVE-Check, Code-Smell-Analyse
7. `context/` — Skeleton-Context, `--get-slice`, HMAC
8. `architecture/` — Constraints-Injection, Test-Generierung
9. `sequence/` — Bigram-Pattern, Sequenz-Validator
10. `security/` — Middleware, Guards, API-Guard
11. `audit_trail/` — OWASP-Mapping (bereits in Phase 1 teilweise)
12. `ac_verification/` — AC-Tag-Registry mit `register_ac_handler()`

**Akzeptanzkriterien Phase 8:**
- Alle Slices unter `samuel/slices/` vorhanden
- `test_no_cross_slice_imports()` grün
- Vollständiger Workflow-Durchlauf (Issue → PR) ohne v1-Code möglich (Bridge noch aktiv)

---

## Phase 9 — Aufräumen

**Abhängigkeit:** Phase 8 vollständig abgeschlossen. Alle Integration-Tests grün.

### Aufgaben

**9.1** `agent_start.py` → `samuel/cli.py` reduzieren (nur CLI-Parsing + Bootstrap-Aufruf)

**9.2** Alle v1-`commands/`-Dateien entfernen (Bridge-Code wurde in Phase 1–8 durch direkte Slice-Nutzung ersetzt)

**9.3** Alle v1-`plugins/`-Dateien entfernen (soweit vollständig migriert)

**9.4** `test_every_v1_file_mapped()` muss vor diesem Schritt 0 unmapped Files melden

**9.5** `repo_patterns.json` neu lernen (vollständig aus v2-Codebase)

**9.6** Sequence-Validator zurück auf Konfigurationswert des Projekts (kann jetzt wieder `block` sein)

**9.7** Dokumentation aktualisieren: `README_technical.md` auf v2-Struktur

**Akzeptanzkriterien Phase 9:**
- Keine `commands/` oder `plugins/` Verzeichnisse mehr (außer Premium)
- `python3 samuel/cli.py --self --doctor` läuft fehlerfrei
- Alle Architecture-Tests grün
- `grep -r "from commands\|from plugins" .` ergibt keine Treffer

---

## Phase 10 — Server-seitiger Hook + Flexibilität

**Abhängigkeit:** Phase 9 abgeschlossen. Framework stabil.

### 10.1 Gitea pre-receive Hook

Schließt die `--no-verify`-Lücke: Client-seitiger Pre-commit Hook ist best-effort. Gitea-Server-Hook ist die echte Schranke.

- Hook-Script auf Gitea-Server deployen
- Prüft mindestens: Branch ≠ main, keine direkten Pushes auf protected Branch
- Setup-Wizard führt Gitea-Admin durch die Installation

### 10.2 GitHub-Support

Jetzt möglich ohne Slice-Änderungen (Port-Abstraktion aus Phase 2):
- `GitHubAdapter` implementieren
- `GitHubAppAuth` (JWT + Installation Token, 60min Rotation)
- Webhook-first Ingress (statt Polling)
- Dashboard-URLs für github.com

### 10.3 Externe Quality-Pipeline (IQualityCheck Registry)

- `IQualityCheck` ABC in `core/ports.py`
- Registry: `CHECKS: dict[str, list[IQualityCheck]]`
- `TreeSitterSyntaxCheck` für TypeScript/Go
- `config/hooks.json` konfiguriert welche Checks für welche Endungen laufen

### 10.4 Weitere Skelett-Builder

- `TreeSitterTSBuilder` (TypeScript/JavaScript)
- `TreeSitterGoBuilder` (Go)
- `SQLBuilder` (Regex-basiert für SQL-Projekte)
- Registry-Eintrag in `config/skeleton_builders.json`

---

## Fortlaufende Aufgaben (alle Phasen)

Diese Punkte laufen parallel zu allen Phasen:

**Sicherheit:**
- Security Tripwire nach jeder Phase testen: Manipulation an kritischen Dateien → CRITICAL-Event
- Hook-Integrität (SHA256) nach jeder Hook-Änderung aktualisieren
- `--doctor` in CI nach jedem Merge auf `main`

**Self-Mode-Parität:**
- Nach jeder Phase: `python3 agent_start.py --self --watch` auf SAMUEL selbst laufen lassen
- Neue Funktionen in `architecture.json:self_mode_parity` eintragen
- Parity-Tests müssen grün bleiben

**Audit-Qualität:**
- Nach jeder Phase: `--doctor --check-owasp` — jedes Event muss OWASP-klassifiziert sein
- `correlation_id` in 100% der Events verifizieren

**Dokumentation:**
- Architecture-Dokument nach jeder Phase aktualisieren (Gate-Nummerierungen, File-Mappings)
- CHANGELOG.md via `--changelog` automatisch generieren

---

## Risiken und Mitigationen

| Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|--------|-------------------|------------|------------|
| Bridge-Code produziert inkonsistente States | Mittel | Hoch | Doppeltes Audit-Log-Schreiben erkennen via `--doctor` |
| Sequence-Validator blockiert v2-Code | Hoch | Niedrig | Warn-only in Phase 0a.5 erzwingen |
| `helpers.py`-Auflösung bricht Edge-Case | Mittel | Mittel | Eine Funktion pro Commit, CI muss grün bleiben |
| Semaphore-Release fehlt in neuem Event | Mittel | Hoch | Terminal-Event-Liste vollständig halten; Semaphore-Leak-Test |
| GitHub-Auth-Token läuft ab während Workflow | Niedrig | Mittel | Circuit Breaker + `IAuthProvider.is_valid()` vor jedem Call |
| Pydantic-Validation bricht bei alten Config-Dateien | Hoch | Niedrig | Legacy-Fallback in Config-Loader; Migrations-Hinweis im Setup-Wizard |
| Self-Mode entwickelt Bypass via Gate-Änderung | Niedrig | Kritisch | Self-Mode-Parity-Tests + Security Tripwire + Hook-Integrität |

---

## Gesamtfortschritt — Checkliste

### Phase 0a — Vorarbeiten
- [ ] 0a.1 Hook-Konvention für beide Welten
- [ ] 0a.2 helpers.py vollständig aufgelöst
- [ ] 0a.3 AgentAbort mit Event-Publishing
- [ ] 0a.4 _cfg() Bridge
- [ ] 0a.5 Sequence-Validator warn-only

### Phase 0b — Shared Kernel
- [ ] 0b.1 samuel/core/ mit allen 10 Dateien
- [ ] 0b.2 Architecture-Tests in Pre-commit
- [ ] 0b.3 Skeleton-Abstraktion (SP)

### Phase 1 — Audit
- [ ] 1.1 audit.py Bridge mit correlation_id
- [ ] 1.2 Audit-Slice
- [ ] 1.3 JSONL-Adapter + Upcaster
- [ ] 1.4 AsyncAuditSink (Security-Events nie verworfen)
- [ ] 1.5 config/audit.json Schema

### Phase 2 — SCM-Port
- [ ] 2.1 IVersionControl vollständig
- [ ] 2.2 GiteaAdapter
- [ ] 2.3 gitea_api.py Bridge
- [ ] 2.4 IAuthProvider (StaticTokenAuth)
- [ ] 2.5 Provider-agnostische Config

### Phase 3 — LLM-Port
- [ ] 3.1 ILLMProvider + LLMResponse
- [ ] 3.2 Alle Adapter (Claude, DeepSeek, Ollama, LMStudio)
- [ ] 3.3 costs.py
- [ ] 3.4 CircuitBreakerAdapter
- [ ] 3.5 SanitizingLLMAdapter (`.text` nicht `.content`)
- [ ] 3.6 plugins/llm.py Bridge

### Phase 4 — Planning-Slice
- [ ] 4.1 Slice-Struktur
- [ ] 4.2 PlanIssueCommand
- [ ] 4.3 3-Stufen LLM-Qualitätskontrolle
- [ ] 4.4 Bridge
- [ ] 4.5 Integration-Test

### Phase 5 — Implementation-Slice
- [ ] 5.1 Slice + llm_loop + patch_parser
- [ ] 5.2 IPatchApplier-Registry
- [ ] 5.3 Resume mit WorkflowCheckpoint
- [ ] 5.4 Semaphore-Release-Verdrahtung
- [ ] 5.5 Bridge

### Phase 6 — PR-Gates-Slice
- [ ] 6.1 Slice + Handler + Gates
- [ ] 6.2 PRGatesHandler mit Bus-Injection
- [ ] 6.3 config/gates.json
- [ ] 6.4 IExternalGate-Infrastruktur
- [ ] 6.5 Bridge

### Phase 7 — Evaluation-Slice
- [ ] 7.1 Slice + scoring.py
- [ ] 7.2 config/eval.json mit Gewichten
- [ ] 7.3 Bridge

### Phase 8 — Alle übrigen Slices
- [ ] 8.1 Watch (Semaphore + Dual-Mode + Hot-Reload)
- [ ] 8.2 Healing (generischer failure_type)
- [ ] 8.3 Dashboard (provider-agnostische URLs + CSRF + Metrics-Endpoint)
- [ ] 8.4 Changelog, Review, Session, Health, Setup, CodeAnalysis, Context, Architecture, Sequence, Security, AuditTrail, ACVerification

### Phase 9 — Aufräumen ✅ (2026-04-16)
- [x] 9.1 cli.py (nur CLI-Parsing)
- [x] 9.2 commands/ entfernen
- [x] 9.3 plugins/ entfernen
- [x] 9.4 test_every_v1_file_mapped + v1→v2 Mapping
- [x] 9.5 repo_patterns.json Persistenz + Validator-Mode
- [x] 9.6 Sequence-Validator verdrahtet (warn, Follow-up #122)
- [x] 9.7 Dokumentation aktualisieren

### Phase 10 — Server-Hook + Flexibilität ✅ (2026-04-17)
- [x] 10.1 Gitea pre-receive Hook (Script + Setup, Follow-up #124 für Deployment)
- [x] 10.2 GitHub-Support (GitHubAdapter + Auth, Follow-up #125 für Webhook-Signatur)
- [x] 10.3 IQualityCheck Registry (4 Checks, per hooks.json konfigurierbar)
- [x] 10.4 Weitere Skeleton-Builder (TS, Go, SQL, Config — 11 Extensions)

### Phase 11 — Compliance (EU AI Act & DSGVO) ✅ (2026-04-17)
- [x] 11.1 DSGVO: PromptSanitizer, Retention, TransferWarning, VVT, DPA
- [x] 11.2 EU AI Act: Attribution, Event-Enrichment, Risikoklassifikation, Tech-Doc

### Phase 12 — Hardening & Modernisierung ✅ (2026-04-17)
- [x] 12.1 Packaging: pyproject.toml, Dockerfile, SECURITY.md, CONTRIBUTING.md
- [x] 12.2 Netzwerk: HttpClientConfig, TLS, Proxy, User-Agent
- [x] 12.3 Testing: 12 Contract-Tests, .pre-commit-config.yaml
- [x] 12.4 Best Practice: ruff clean (208 Fixes), mypy Config

### Phase 13 — Vergessenes & Konzeptfehler ✅ (2026-04-17)
- [x] 13.1-13.4 Config: Hardcoded-Werte extrahiert (agent.json + llm/defaults.json)
- [x] 13.5-13.6 LLM: v2-Adapter einheitlich, v3-Kandidaten dokumentiert
- [x] 13.7 Security: E7 Code-Injection GEFIXT (Whitelist + Path-Traversal)
- [x] 13.8-13.10 Security: v2-Design löst P1-P3, RBAC als v3-Kandidat
- [x] 13.11 Events: 8 neue Event-Typen (N1-N5)
- [x] 13.12 Architektur: M3 Semaphore-Leak GEFIXT (5 Terminal-Events)
- [x] 13.13-13.22 Rest: v2-Neubau hat v1-Probleme vermieden
