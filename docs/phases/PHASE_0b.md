# Phase 0b — Shared Kernel bauen

> Quelle: SAMUEL_V2_UMSETZUNGSPLAN.md Zeile 186-249
> Architektur-Referenz: SAMUEL_ARCHITECTURE_V2.1.md Kapitel 4 + 5

## Aufgabe 0b.1 — samuel/core/ anlegen

Dateien in dieser Reihenfolge (zirkuläre Importe vermeiden):

1. `errors.py` — AgentAbort, SecurityViolation, GateFailed, ProviderUnavailable
2. `types.py` — LLMResponse, GateContext, GateResult, AuditQuery, SkeletonEntry, safe_int, safe_float, strip_html, validate_comment
3. `ports.py` — alle IXxx ABCs (importiert nur types + errors)
4. `events.py` — alle Event-Typen als Dataclasses mit event_version, correlation_id, causation_id. Timestamp: `datetime.now(timezone.utc)` NICHT `datetime.utcnow()`
5. `commands.py` — alle Command-Typen mit idempotency_key
6. `config.py` — IConfig-Implementierung + **Pydantic-Schemas** (NICHT Dataclasses) für alle Config-Dateien
7. `logging.py` — Logging-Setup
8. `bus.py` — Bus + alle 6 Middlewares:
   - IdempotencyMiddleware (threading.Lock + persistierter Store + TTL 24h)
   - SecurityMiddleware
   - PromptGuardMiddleware
   - AuditMiddleware
   - ErrorMiddleware
   - MetricsMiddleware
9. `workflow.py` — WorkflowEngine mit has_handler()-Check + UnhandledCommand-Event
10. `bootstrap.py` — Startup-Sequenz (Steps 1-3 implementiert, 4-12 als Stubs mit TODO — Adapter/Slices kommen in späteren Phasen)

## Aufgabe 0b.2 — Architecture-Tests

Datei: `tests/test_architecture_v2.py`

Vollständig implementieren:
- `test_no_cross_slice_imports()` — prüft samuel/slices/**/*.py Imports
- `test_no_direct_adapter_usage()` — Slices importieren keine Adapter
- `test_shared_kernel_minimal()` — erlaubt: bus, events, commands, ports, types, errors, config, logging, workflow, bootstrap, __init__
- `test_no_module_level_config()` — kein Slice importiert settings direkt

Als Stub anlegen (erst in späteren Phasen sinnvoll):
- `test_every_v1_file_mapped()` — Stub mit `pytest.skip("Erst sinnvoll wenn v1-Migration läuft")`
- `test_all_gates_have_owasp()` — Stub mit `pytest.skip("Braucht gates.json, kommt in Phase 6")`
- `test_event_types_complete()` — vollständig implementieren (AST-Scan von events.py → Test-Coverage prüfen)

**Pre-commit Hook einrichten:** `tests/test_architecture_v2.py` muss bei jedem Commit laufen.

## Aufgabe 0b.3 — Skeleton-Abstraktion

- `ISkeletonBuilder` ABC bereits in ports.py (aus 0b.1)
- `SkeletonEntry` Dataclass bereits in types.py (aus 0b.1)
- `PythonASTBuilder` als erste Implementierung: Logik aus v1 `context_loader.py` NEU schreiben
- Registry: `SKELETON_BUILDERS: dict[str, ISkeletonBuilder]`
- Neues `language`-Feld in SkeletonEntry

**Akzeptanzkriterien 0b.3:**
- PythonASTBuilder extrahiert Funktionen/Klassen aus einer .py Datei
- SkeletonEntry enthält name, kind, file, line_start, line_end, calls, called_by, language
- Unit-Tests mit einer kleinen .py Beispieldatei

**NICHT anwendbar (v2 hat diese Systeme noch nicht):**
- `python3 agent_start.py --self --build-skeleton` — v2 hat keinen agent_start.py
- "Alle 5 abhängigen Systeme funktionsfähig" — kommen erst in späteren Phasen

## Definition of Done

- [ ] samuel/core/ mit allen 10 Dateien
- [ ] Alle Typen vollständig (LLMResponse, GateContext, GateResult, SkeletonEntry, AuditQuery)
- [ ] config.py nutzt **Pydantic** (nicht Dataclasses)
- [ ] Bus + 6 Middlewares implementiert und getestet
- [ ] IdempotencyMiddleware: threading.Lock + persistiert + TTL
- [ ] WorkflowEngine mit UnhandledCommand-Event bei fehlendem Handler
- [ ] Bootstrap: Steps 1-3 implementiert, 4-12 Stubs
- [ ] Architecture-Tests angelegt, Pre-commit Hook aktiv
- [ ] Skeleton-Abstraktion: ISkeletonBuilder + PythonASTBuilder + Tests
- [ ] `python3 -m pytest tests/ samuel/ -v` → alle grün
