# S.A.M.U.E.L. — Technische Dokumentation (EU AI Act)

> Gemaess Art. 11, Annex IV EU AI Act (VO 2024/1689)

**Stand:** 2026-04-17

---

## 1. Allgemeine Beschreibung (Annex IV Nr. 1)

**Name:** S.A.M.U.E.L. — Sicheres Autonomes Mehrschichtiges Ueberwachungs- und Entwicklungs-Logiksystem

**Zweck:** Automatisierte, kontrollierte Software-Entwicklung unter menschlicher Aufsicht. Das System nimmt Issues entgegen, generiert Plaene und Code via LLM, bewertet Ergebnisse und erstellt Pull Requests.

**Risikoklasse:** Limited Risk (Art. 50 — Transparenzpflichten)

**Nicht-Verwendung fuer:** Biometrie, kritische Infrastruktur, Beschaeftigungsentscheidungen, Strafverfolgung.

## 2. Architektur (Annex IV Nr. 2)

### 2.1 Systemarchitektur

Event-Driven Monolith mit Vertical Slices:

```
CLI / Webhook → Bootstrap → Bus (6 Middlewares) → WorkflowEngine
                                    ↓
                    ┌───────────────┤───────────────┐
                    ↓               ↓               ↓
              Planning-Slice  Implementation  Evaluation
                    ↓               ↓               ↓
              LLM-Provider    Patch-Parser    Score-Pipeline
                    ↓               ↓               ↓
              PR-Gates ←────────────┘───────────────┘
                    ↓
              Pull Request (mit AI-Attribution)
```

### 2.2 Kernkomponenten

| Komponente | Funktion | Dateien |
|-----------|----------|---------|
| Shared Kernel | Bus, Events, Commands, Config, Ports | `samuel/core/` (10 Module) |
| Feature Slices | Vertikale Funktionseinheiten | `samuel/slices/` (21 Slices) |
| Adapters | Externe Systeme (LLM, SCM, Audit) | `samuel/adapters/` (8 Adapter-Gruppen) |
| Quality-Pipeline | Syntax, Scope, Size Checks | `samuel/adapters/quality/` |
| Skeleton-Builder | Code-Analyse (11 Sprachen) | `samuel/adapters/skeleton/` |

### 2.3 Middleware-Kette

Jeder Command/Event durchlaeuft 6 Middlewares:

1. **IdempotencyMiddleware** — Deduplizierung
2. **SecurityMiddleware** — Blockiert verbotene Muster
3. **PromptGuardMiddleware** — Pflicht-Marker in LLM-Prompts
4. **AuditMiddleware** — Protokollierung mit Correlation-ID
5. **ErrorMiddleware** — Exception-Handling
6. **MetricsMiddleware** — Latenz und Fehler-Zaehler

## 3. Datenfluesse (Annex IV Nr. 3)

### 3.1 Issue → Plan

```
Gitea/GitHub Issue → IVersionControl → PlanIssueCommand
  → PromptSanitizer (PII-Scrubbing)
  → PromptGuardMiddleware (Pflicht-Marker)
  → ILLMProvider.complete()
  → PlanValidated / PlanBlocked
  → AuditEvent (mit prompt_hash, model_version)
```

### 3.2 Plan → Code

```
ImplementCommand → Context-Loading (Skeleton + Slices)
  → LLM-Loop (max 5 Runden)
  → PatchParser → PatchApplier
  → QualityChecks (Syntax, Scope, Size)
  → EvaluateCommand → Score-Pipeline
  → PRGatesHandler → 14 Gates
  → PR (mit AI-Generated-By Trailer)
```

### 3.3 Daten an externe Systeme

| Empfaenger | Daten | Schutzmassnahme |
|-----------|-------|-----------------|
| LLM-Provider | Issue-Text (PII-bereinigt), Code-Kontext | PII-Scrubbing, TLS |
| SCM (Gitea/GitHub) | Commits, PR-Bodies, Kommentare | Token-Auth, TLS |
| Dashboard (lokal) | Aggregierte Metriken | CSRF-Schutz |

## 4. Risikomanagement (Annex IV Nr. 4)

### 4.1 Identifizierte Risiken

| Risiko | Mitigation |
|--------|-----------|
| LLM generiert unsicheren Code | 14 PR-Gates, ScopeGuard, Secret-Scanner |
| PII in LLM-Prompts | PromptSanitizer (config/privacy.json) |
| Halluzinierte Funktionen | Hallucination-Guard via Skeleton-Abgleich |
| Unkontrollierte Aenderungen | Gate-System, Semaphore, Branch-Protection |
| Prompt-Injection | PromptGuardMiddleware, Security-Middleware |

### 4.2 Restrisiken

| Risiko | Bewertung | Begruendung |
|--------|-----------|------------|
| LLM-Bias in Code-Stil | Niedrig | Code wird durch Gates + Eval geprueft |
| False Negatives im Secret-Scanner | Niedrig | Regex + OWASP-Patterns, aber nicht vollstaendig |
| Provider-Ausfall | Mittel | Circuit-Breaker + Provider-Fallback |

## 5. Monitoring und Logging (Annex IV Nr. 5)

- **Audit-Trail:** JSONL mit Correlation-IDs, OWASP-Klassifikation
- **Metriken:** Commands/Events pro Typ, Fehlerrate, Latenz
- **Dashboard:** Echtzeit-Status auf Port 7777
- **Retention:** 365 Tage, PII nach 30 Tagen anonymisiert
- **Health-Check:** `samuel health` fuer System-Selbstdiagnose

## 6. Aenderungsprotokoll

| Datum | Aenderung |
|-------|-----------|
| 2026-04-17 | Erstversion — Phase 11 (Compliance) |
