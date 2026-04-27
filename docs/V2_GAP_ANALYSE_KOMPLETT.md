# S.A.M.U.E.L. v2 — Vollständige Gap-Analyse (v1 ↔ v2 ↔ 2026 Best Practice)

> Stand: 2026-04-16 | Basiert auf: vollständiger v1-Codebase-Analyse + SAMUEL_ARCHITECTURE_V2.1.md + SAMUEL_V2_UMSETZUNGSPLAN.md
> Ziel: Alle fehlenden Features, Prozesslücken, Hardcoded-Werte, Security-/Compliance-Gaps und Modernisierungen identifizieren und in diesem Dokument hinzufügen.

---

## Was ist v1?

**v1 = der bestehende Code im Repository `S.A.M.U.E.L.-main`** — der aktuelle Monolith mit folgender Struktur:

```
S.A.M.U.E.L.-main/
  agent_start.py          ← Zentraler Einstiegspunkt (1267 Zeilen, ~60 Delegate-Funktionen)
  settings.py             ← Konfiguration (666 Zeilen, .env + config/agent.json)
  gitea_api.py            ← Gitea REST API Client (620 Zeilen)
  evaluation.py           ← Eval-System: HTTP-Tests + Score-Vergleich (987 Zeilen)
  helpers.py              ← Shared Helper (431 Zeilen, teilweise dupliziert in agent_start.py)
  context_loader.py       ← Skeleton, Datei-Erkennung, AST-Analyse
  code_analyzer.py        ← AST-basierte Code-Smell-Analyse
  issue_helpers.py        ← Risiko-Klassifikation, Branch-Name-Generierung
  session.py              ← Session-Tracking (Limit, Cooldown)
  workspace.py            ← Workspace-Pfade (open/, done/)
  agent_self_check.py     ← Startup-Validierung (849 Zeilen)
  commands/               ← 20 Command-Module (auto, plan, implement, implement_llm, pr, watch, heal, review, ...)
  plugins/                ← 28 Plugins (audit, llm, quality_pipeline, healing, ac_verification, patch, ...)
  config/                 ← agent.json, agent_eval.json, llm/routing.json, llm/prompts/, llm/ide/
  dashboard/              ← Web-Dashboard (6 Tabs: Status, LLM, Workflow, Logs, Health, Security)
```

**Kernproblem v1:** Enge Kopplung, zirkuläre Lazy-Imports (`_get_gitea()`, `_get_project()` in jedem Modul), duplizierte Logik (z.B. `_strip_html()` 4-fach, `_validate_comment()` 2-fach, Implementierungs-Block in `auto.py` wörtlich dupliziert). Jeder Bugfix kann Seiteneffekte in 3+ Modulen auslösen. Das Programm ist nie produktiv gelaufen.

**v2 = die neue Event-Bus-Architektur** beschrieben in `SAMUEL_ARCHITECTURE_V2.1.md` mit Umsetzungsplan in `SAMUEL_V2_UMSETZUNGSPLAN.md`. Code bis Phase 8 abgeschlossen (nicht in diesem Repository enthalten).

---

## LLM-Anweisung für Folge-Scans

> **Prompt für nächsten Durchgang:**
> Du bist ein Senior Software Architect mit Expertise in Event-Driven Architecture, LLM-Orchestrierung, OWASP Agentic AI Top 10, EU AI Act und DSGVO.
>
> Lies die folgenden drei Dokumente:
> 1. Diese Gap-Analyse (V2_GAP_ANALYSE_KOMPLETT.md)
> 2. SAMUEL_ARCHITECTURE_V2.1.md
> 3. SAMUEL_V2_UMSETZUNGSPLAN.md
>
> Deine Aufgabe: Finde **weitere Findings** die in dieser Gap-Analyse noch fehlen. Prüfe auf:
> - Vergessene v1-Funktionen die in v2 nicht abgebildet sind
> - Fehlende Error-Handling-Pfade
> - Architektur-Inkonsistenzen zwischen Architektur-Dokument und Umsetzungsplan
> - Weitere 2026 Best Practices (Goldstandard) die fehlen
> - EU AI Act Artikel die nicht adressiert sind
> - DSGVO-Anforderungen die fehlen
> - Fehlende Konfigurationsoptionen
> - Fehlende Events/Commands im Bus-Design
>
> Ausgabeformat: Gleiche Tabellen-Struktur wie in dieser Datei. Neue Findings mit Nummern ab K1, L1 etc.
> Bestätige explizit welche Findings aus dieser Analyse du als vollständig und korrekt einstufst.
>
> **Kontexthinweis:** S.A.M.U.E.L. ist Apache-2.0 lizenziert. LLM-Routing + Nacht-Routing + Token-Kostenanalyse-Aggregation sind ein kostenpflichtiges Premium-Plugin. Alles andere ist Kern. GitHub-Support ist in Arbeit. Benutzersystem mit Rollen ist geplant.

---

## Durchgang 1: Fehlende Features & Provider

### A. Fehlende Features / Provider in v2-Architektur

| # | Was in v1 existiert | In v2 erwähnt? | Handlungsbedarf |
|---|--------------------|----|---|
| **A1** | **OpenRouter als Pricing-Quelle** (`llm_costs.py`: 350+ Modelle, Cache, `refresh_pricing()`, 24h-TTL) | ❌ Nicht erwähnt | Apache-Kern. `adapters/llm/costs.py` muss OpenRouter-Pricing-Cache enthalten. Meta-Service, kein Provider. Ggf. `IPricingProvider`-Port |
| **A2** | **OpenRouter als Universal-Provider** (v1 `routing.json` zeigt `groq_via_openai`-Beispiel = OpenRouter-Pattern) | ❌ Nur Claude/DeepSeek/Ollama/LMStudio als Adapter | Apache-Kern. `OpenRouterAdapter` als eigener Adapter (OpenAI-kompatibel aber eigene base_url + Model-ID-Mapping). Nicht nur ein "OpenAI mit anderer URL"-Hack |
| **A3** | **Gemini-Provider** (`GeminiClient` in `llm.py` mit eigenem API-Format: `generateContent`, `systemInstruction`) | ⚠️ Nicht in v2-Adapter-Liste (nur Claude/DeepSeek/Ollama/LMStudio) | Apache-Kern. `GeminiAdapter` fehlt in v2, obwohl v1 ihn hat und `routing.json` ihn aktiv für `issue_analysis`, `healing`, `deep_coding` nutzt |
| **A4** | **LLM-Routing per Task** (`routing.json`: 10 Tasks mit eigenem Provider/Modell/Timeout/Prompt) | ✅ Als Premium-Plugin erwähnt | Premium. Aber: `routing.json`-Format + Task-Registry (`issue_analysis`, `implementation`, `pr_review`, `test_generation`, `log_analysis`, `healing`, `docs`, `deep_coding`, `planning`) sollte als `ITaskRouter`-Port definiert sein |
| **A5** | **System-Prompt pro Task** (`routing.json`: `system_prompt: "senior_python.md"`, 7 verschiedene Prompt-Dateien) | ✅ PromptGuardMiddleware | OK — aber Prompt-Dateien müssen in v2 mitmigriert werden: `senior_python.md`, `planner.md`, `reviewer.md`, `healer.md`, `analyst.md`, `docs_writer.md`, `log_analyst.md` |
| **A6** | **CLI-Command pro Task** (`routing.json`: `cli_cmd: "claude"` für interaktive Sessions via `context_export.sh`) | ❌ Nicht in v2 | CLI-Integration für interaktive Sessions muss im CLI-Slice bleiben |
| **A7** | **Hardcoded Fallback-Preise** (`_COST_PER_1M` Tabelle: 14 Modelle + 7 Provider-Fallbacks in `llm_costs.py`) | ❌ | Apache-Kern. Muss in v2 `adapters/llm/costs.py` als Offline-Fallback existieren |
| **A8** | **`_client_from_env()` Fallback-Kette** (DeepSeek → Claude → LMStudio → Local) mit Default-System-Prompt | ❌ Nicht dokumentiert | Provider-Fallback-Reihenfolge muss konfigurierbar sein: `config/agent.json → llm.provider_priority: ["deepseek", "claude", "local"]` |
| **A9** | **Premium-Plugin-Hook** (`install_router()`, `install_get_client()` — globale Registrierung) | ⚠️ Premium erwähnt, Hook-Mechanismus nicht | v2: Plugin registriert sich auf den Bus und überschreibt den Default-Handler. Kein globales `_router`-Variable-Pattern mehr |

### B. Hardcoded Werte die zentral konfigurierbar sein müssen

| # | Wert | Wo in v1 | v2-Status | Ziel-Config-Pfad |
|---|------|----------|-----------|-----------------|
| **B1** | `max_tokens: 4096` Default pro Task | `routing.json` | ⚠️ | `config/llm/routing.json → tasks.*.max_tokens` |
| **B2** | `timeout: 60` Default pro Task | `routing.json` | ⚠️ | `config/llm/routing.json → tasks.*.timeout` |
| **B3** | `temperature: 0.2` — in JEDEM Client hardcoded | `llm.py` Zeile 168, 252, 278 | ❌ | `config/llm/routing.json → tasks.*.temperature` (Healing braucht ggf. 0.4, Planning 0.1) |
| **B4** | `TIMEOUT = 10` (Eval HTTP-Request) | `evaluation.py` Zeile 62 | ❌ | `config/agent_eval.json → request_timeout` |
| **B5** | `HISTORY_MAX = 90` (Score-History) | `evaluation.py` Zeile 61 | ❌ | `config/agent.json → eval.history_max` |
| **B6** | `_MAX_RETRIES = 2` (Gitea API) | `gitea_api.py` Zeile 82 | ❌ | `config/agent.json → scm.max_retries` |
| **B7** | `_TRANSIENT_HTTP_CODES = (502, 503, 504)` | `gitea_api.py` Zeile 81 | ❌ | `config/agent.json → scm.transient_codes` |
| **B8** | `_GIT_TIMEOUT = 30` | `helpers.py` Zeile 47 | ❌ | `config/agent.json → git.timeout` |
| **B9** | `poll_interval = 30`, `poll_timeout = 7200` | `commands/auto.py` Zeile 558-559 | ❌ | `config/agent.json → auto.poll_interval`, `auto.poll_timeout` |
| **B10** | `_CACHE_MAX_AGE = 86400` (24h Pricing-Cache) | `llm_costs.py` Zeile 14 | ❌ | `config/agent.json → llm.pricing_cache_hours` |
| **B11** | `FAILURE_THRESHOLD = 3`, `COOLDOWN_SECONDS = 120` (CircuitBreaker) | v2-Architektur | ⚠️ Im Code, nicht in Config | `config/llm/providers.json → per_provider.circuit_breaker` |
| **B12** | `time.sleep(2)` zwischen Eval-Steps | `evaluation.py` Zeile 247 | ❌ | `config/agent_eval.json → step_delay_seconds` |
| **B13** | `max_tokens: 1024` Default in Client-Konstruktoren | `llm.py` (alle 6 Clients) | ❌ | `config/llm/routing.json → default.max_tokens` (existiert als 4096, aber Env-Fallback-Clients ignorieren es) |
| **B14** | Context-Window-Größen pro Modell | Nirgends in v1 oder v2 | ❌ Fehlt komplett | `config/llm/models.json` oder aus OpenRouter-Cache. Kritisch für Slice-Request-Loop |
| **B15** | `API_VERSION = "2023-06-01"` (Anthropic) | `llm.py` ClaudeClient | ❌ | Muss aktualisierbar sein ohne Code-Change |
| **B16** | `_COOLDOWN_SECONDS = 300`, `_MAX_RETRIES = 3` (Resume) | `plugins/resume.py` Zeile 38-39 | ❌ | `config/agent.json → resume.cooldown_seconds`, `resume.max_retries` |
| **B17** | `_MAX_CONSECUTIVE_ERRORS = 5` (Watch-Loop) | `commands/watch.py` Zeile 27 | ❌ | `config/agent.json → watch.max_consecutive_errors` |
| **B18** | `_SPIKE_THRESHOLD = 3` (Log-Anomalie) | `plugins/log_anomaly.py` Zeile 89 | ❌ | `config/agent.json → watch.anomaly_spike_threshold` |
| **B19** | `diff_trunc = diff[:6000]` (PR-Review) | `commands/review.py` Zeile 40 | ❌ | `config/agent.json → review.max_diff_chars` |
| **B20** | `failed[:3]` (max 3 Tests pro Heal) | `commands/heal.py` Zeile 85 | ❌ | `config/agent.json → healing.max_tests_per_run` |
| **B21** | `REQUIRED_MARKERS` (7 Pflicht-Strings für LLM-Config) | `llm_config_guard.py` Zeile 36-43 | ❌ | `config/agent.json → security.required_markers` |
| **B22** | `_RESTART_PATTERNS` (Server-Dateien) | `commands/pr.py` Zeile 53-59 | ❌ | `config/agent_eval.json → restart_patterns` |

### C. Strukturelle Verbesserungen

| # | Thema | Problem | Empfehlung |
|---|-------|---------|------------|
| **C1** | **Settings-Tab / Admin-UI** | Kein Settings-Tab. Alle Änderungen erfordern Datei-Edit | **Settings-Slice** mit REST-API (`GET/PUT /api/settings/{section}`) + Dashboard-Tab. Publiziert `ConfigChanged`-Events. Widerspricht NICHT der Bus-Architektur |
| **C2** | **Zentrales Model-Registry** | Modelle in `routing.json`, Preise in `llm_costs.py`, Context-Windows nirgends | Ein `models.json`: `{id, context_window, pricing, capabilities, provider}`. OpenRouter-Cache als Quelle, manuell überschreibbar |
| **C3** | **Provider-Health-Anzeige** | Kein Tracking ob ein Provider erreichbar ist | CircuitBreaker-State im Dashboard. `/api/providers` Endpoint: healthy/degraded/down |
| **C4** | **Rate-Limit-Awareness** | `429`-Erkennung nur als Boolean `token_limit_hit` | `Retry-After`-Header auswerten. Backoff pro Provider. `ProviderRateLimited`-Event auf Bus |
| **C5** | **Streaming-Support** | Alle Clients synchron | `ILLMProvider.complete(stream=True)` als Capability vorbereiten. Für Token-Limit-Erkennung während Generierung |
| **C6** | **Structured Output** | Freitext-Parsing für Patches (`SEARCH/REPLACE`, `REPLACE LINES`) | OpenAI/Gemini: `response_format: {type: "json_schema"}`. Claude: Tool-Use. Als `ILLMProvider`-Capability. Größter Qualitätssprung bei Patches |
| **C7** | **Token-Counting lokal** | `chars / 4` Heuristik (`context_compactor.py`) | `tiktoken` oder `anthropic.count_tokens()`. Exakte Zählung VOR dem Call verhindert abgeschnittene Responses |
| **C8** | **Multi-Tenant Config-Isolation** | `.env` + `agent.json` = ein Projekt | Wenn Benutzersystem kommt: `IConfig.get(key, scope=user_id)` |
| **C9** | **Secrets-Management** | Alles in `.env` Plaintext | `ISecretsProvider`-Port definiert aber kein Enterprise-Adapter (Vault/AWS Secrets Manager) |
| **C10** | **Observability / OpenTelemetry** | JSONL-Audit + `get_logger()` | OTel SDK: Traces + Metrics + Logs. `OTelAuditAdapter` neben `JSONLAdapter`. 2026 Standard |
| **C11** | **Config-Diff bei Reload** | `settings.reload()` überschreibt blind | `ConfigReloaded`-Event mit `changed_keys: list[str]`. Slices reagieren nur bei relevanten Änderungen |
| **C12** | **Cached Tokens** | `LLMResponse` hat kein `cached_tokens` | Anthropic `cache_read_input_tokens`, DeepSeek ähnlich. Kostenberechnung ohne cached_tokens ungenau |

---

## Durchgang 2: Security, RBAC & Compliance

### E. Security-Gaps

| # | Thema | v1-Status | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **E1** | **RBAC / Benutzersystem** | ❌ Ein Bot-User, keine Rollen | ⚠️ "Single-Tenant by Design" | `IIdentityProvider` + `Role`-Enum (`admin`, `developer`, `reviewer`, `readonly`). `SecurityMiddleware` prüft `user.has_permission(command.required_role)`. Jeder Command braucht `required_role` |
| **E2** | **API-Key-Rotation** | ❌ Statische Tokens, kein Ablauf | ⚠️ `IAuthProvider.refresh()` definiert | `IAuthProvider.is_valid()` + `expires_at`. Dashboard-Alert 7 Tage vor Ablauf |
| **E3** | **Secrets in Audit-Log** | ⚠️ `meta`-Dicts könnten Tokens enthalten | ❌ Kein Scrubbing | `AuditMiddleware` mit Regex-Scrubber: `sk-...`, `ghp-...`, `glpat-...` → `***REDACTED***` |
| **E4** | **Prompt Injection über Issue-Body** | ⚠️ `_strip_html()` schützt HTML, nicht Prompt-Injection | ✅ XML-Delimiter beschrieben | Umsetzen: alle Prompts mit User-Input brauchen `<user_controlled_content>`-Tags |
| **E5** | **Keine Signatur auf Audit-Log** | ❌ JSONL Plaintext, manipulierbar | ❌ | HMAC-Chain: jede Zeile enthält Hash der vorherigen. `--doctor` prüft Integrität |
| **E6** | **Bot-Token-Scope nicht geprüft** | ⚠️ Erwähnt, nicht implementiert | ✅ Schicht 4 | Umsetzen: `/api/v1/user` prüfen ob `is_admin: false` |
| **E7** | **Code-Injection via AC-Tag `[IMPORT]`** | ⚠️ `ac_verification.py` Z.176: `subprocess.run([python, "-c", f"import {tag_arg}"])` — tag_arg aus Issue-Body! | ❌ | **KRITISCH**: `[IMPORT] os; os.system('rm -rf /')` wird ausgeführt. Whitelist: `tag_arg` nur `[a-zA-Z0-9_.]` |
| **E8** | **`grep` mit User-Input** | ⚠️ `ac_verification.py`: `subprocess.run(["grep", "-r", tag_arg])` | ❌ | Regex-Injection. `--fixed-strings` Flag oder Sanitization |
| **E9** | **Dashboard ohne Auth/Rate-Limit** | ❌ Offener HTTP-Server | ⚠️ CSRF erwähnt | Auth-Middleware + Rate-Limiter auf `/api/*`. Ohne Auth ist `/api/settings` ein offenes Tor |
| **E10** | **Agent-Lock Race Condition** | ⚠️ PID-basiert, nicht atomar | ✅ `IdempotencyMiddleware` | OK wenn umgesetzt |
| **E11** | **`--no-verify` Bypass** | ⚠️ Nur Post-hoc-Erkennung | ✅ Server-Hook Phase 10 | Prio erhöhen. Ohne Server-Hook ist Schicht 3 best-effort |

### F. EU AI Act (2024/1689) & DSGVO

| # | Anforderung | Quelle | Status | Handlungsbedarf |
|---|-------------|--------|--------|-----------------|
| **F1** | **Menschliche Aufsicht (Human Oversight)** | AI Act Art. 14 | ✅ Plan → Freigabe → Merge = Human-in-the-Loop | Dokumentieren als USP. Art. 14 by Design |
| **F2** | **KI-generierter Code kennzeichnen** | AI Act Art. 50 (1) | ⚠️ `llm_attribution` Feature-Flag, optional | **Pflicht machen**. Git-Trailer: `AI-Generated-By: claude-sonnet-4-6 via S.A.M.U.E.L.` maschinenlesbar |
| **F3** | **Datenminimierung bei LLM-Calls** | DSGVO Art. 5 (1c) | ❌ Issue-Body vollständig in Prompt, ggf. PII | `PromptSanitizer`: E-Mail, IP-Adressen scrubben vor LLM-Call. `config/privacy.json` mit Scrub-Regeln |
| **F4** | **Recht auf Erklärung** | AI Act Art. 86, DSGVO Art. 22 | ⚠️ Audit-Log existiert | Jeder `LLMCallCompleted`-Event braucht: `prompt_hash`, `system_prompt_version`, `temperature`, `model_version`. Nicht den Prompt selbst |
| **F5** | **Aufbewahrungsfrist Audit-Logs** | DSGVO Art. 5 (1e) | ⚠️ `retention_days = 10` — zu kurz | Konfigurierbar: `config/audit.json → retention_days`. Default 365. PII nach 30 Tagen anonymisieren |
| **F6** | **Verzeichnis der Verarbeitungstätigkeiten** | DSGVO Art. 30 | ❌ | `docs/DSGVO_VVT.md`: welche Daten → wohin (Issue-Text → LLM-API → Response → Git). Sub-Prozessoren: Anthropic, Google, DeepSeek |
| **F7** | **Data Processing Agreement** | DSGVO Art. 28 | ❌ | DPA-Templates pro Provider. Dashboard-Hinweis wenn Provider ohne DPA |
| **F8** | **Technische Dokumentation** | AI Act Art. 11, Annex IV | ⚠️ README_technical.md existiert | `docs/AI_ACT_TECHNICAL_DOC.md`: Zweckbestimmung, Funktionslogik, Leistungskennzahlen, Risikobewertung |
| **F9** | **Risikoklassifikation** | AI Act Art. 6 | ❌ | "Limited Risk" klassifizieren (Transparenzpflichten). Kein "High Risk" für Code-Generierung — außer bei kritischer Infrastruktur |
| **F10** | **Provider-Wechsel ohne Datenverlust** | DSGVO Art. 20 | ✅ Provider-agnostisch, Audit lokal | OK |
| **F11** | **Recht auf Löschung** | DSGVO Art. 17 | ❌ Kein Löschmechanismus | `DeleteUserDataCommand`: löscht Audit-Events, Workspace, Score-History pro User/Issue |
| **F12** | **Drittland-Transfer** | DSGVO Art. 44-49 | ❌ Claude=US, DeepSeek=China, Gemini=US | Dashboard-Warnung pro Provider. `config/privacy.json → allowed_regions: ["EU"]`. Blockiert Provider außerhalb erlaubter Regionen |

---

## Durchgang 3: Workflow-Robustheit & Error-Recovery

### G. Workflow-Gaps

| # | Thema | v1-Status | v2-Handlungsbedarf |
|---|-------|-----------|-------------------|
| **G1** | **Partial Failure bei Multi-Step-Implementierung** | ⚠️ Patches 1+2 bleiben bei Fehler in Patch 3. Kein Rollback | Transaktionale Semantik: `git stash` vor Start. Bei Failure: `git stash pop`. Oder Checkpoint pro Patch |
| **G2** | **PR erstellt aber Eval fehlgeschlagen** | ⚠️ Race bei `--force` | Gate 10 **vor** `create_pr()`. In v2: `CreatePRCommand` erst nach `EvalPassed`-Event |
| **G3** | **Kein Rollback nach Auto-Merge** | ❌ `auto_merge_pr` ohne Undo | `PostMergeEvalCommand`: Eval nach Merge. Bei Regression: `git revert` + Issue |
| **G4** | **Watch-Loop Starvation** | ⚠️ Langes `cmd_implement_llm()` blockiert alles | v2 Semaphore + `implementation_timeout` pro Issue (Default 30min). `WorkflowTimeout`-Event |
| **G5** | **Stale Branch Detection** | ⚠️ Gate 13a/13b erwähnt, aber: wann "abandoned"? | `BranchStalenessCheck` im Watch-Slice: ohne Commits seit X Tagen → Warnung. `branches.stale_days: 14` |
| **G6** | **Kein Dead-Letter-Queue** | ❌ Fehlgeschlagene Commands gehen verloren | Bus-DLQ: nach N Retries → `data/dlq.json`. Dashboard-Tab. Manueller Retry-Button |
| **G7** | **Label-State-Machine nicht formalisiert** | ⚠️ Übergänge implizit, `_fix_label_consistency` repariert post-hoc | Formale State-Machine: `ready → proposed → progress → review → closed`. `InvalidLabelTransition`-Event |
| **G8** | **Keine Prioritäts-Queue** | ❌ Nur Risikostufe-Sort | `priority = risk * urgency_factor`. Labels `critical`/`hotfix` erhöhen Priorität |
| **G9** | **Resume verliert LLM-Kontext** | ⚠️ Speichert Issue/Task/Provider, nicht Dialog-History | `WorkflowCheckpoint` mit `conversation_history` (letzte N Messages). Sonst: LLM beginnt von vorne |
| **G10** | **Kein Dry-Run-Modus** | ❌ | `DryRunMiddleware`: fängt SCM-Write-Commands ab, loggt statt ausführt. Für Onboarding/Testing |

---

## Durchgang 4: Testing & CI

### H. Testing-Gaps

| # | Thema | Status | Handlungsbedarf |
|---|-------|--------|-----------------|
| **H1** | **Keine Contract-Tests für Ports** | ❌ | Abstrakte Testklasse pro Port. `test_contract_scm.py`: `create_pr()` muss `url` + `number` liefern — egal welcher Adapter |
| **H2** | **Keine Integration-Tests für Bus** | ❌ | E2E: `PlanIssueCommand` → Bus → Handler → `PlanCreated` → Subscriber. Mock-SCM + Mock-LLM |
| **H3** | **Architecture-Tests nicht in CI** | ⚠️ | `test_no_cross_slice_imports()`, `test_no_direct_adapter_usage()` in Pre-commit UND CI. Blocker, nicht Warnung |
| **H4** | **Kein Chaos-Testing** | ❌ | Simuliere: LLM-Timeout mitten im Patch, Gitea weg nach Label-Swap, Disk voll beim Audit-Write. Kein Datenverlust? |
| **H5** | **Keine Performance-Baseline** | ⚠️ | `MetricsMiddleware` sammelt Laufzeiten pro Command. Dashboard-Trend. Alert bei 3x Slowdown |
| **H6** | **Mock-LLM nicht deterministisch** | ⚠️ | Deterministic-Mock: `prompt_hash → fixture_response`. Snapshot-Testing |
| **H7** | **Keine Mutation-Tests** | ❌ | `mutmut`/`cosmic-ray`: "Gate 7 auskommentiert → Test schlägt fehl?" Sonst: Test-Coverage = Illusion |
| **H8** | **Test-Isolation** | ⚠️ | Tests lesen echte `.env`. Jeder Test muss `IConfig`-Mock nutzen. In v2 per Constructor-Injection lösbar |

---

## Durchgang 5: 2026 Best Practice & Modernisierungen

### I. Elegantere Lösungen

| # | Thema | Aktuell | 2026 Best Practice | Aufwand |
|---|-------|---------|-------------------|---------|
| **I1** | Token-Counting | `chars / 4` | `tiktoken` oder `anthropic.count_tokens()`. Exakt vor dem Call | Mittel |
| **I2** | Structured Output | Freitext-Parsing | `response_format: {type: "json_schema"}` (OpenAI/Gemini), Tool-Use (Claude). Kein Parser-Fehler mehr | Hoch — größter Impact |
| **I3** | LLM-Response-Caching | Kein Caching | Semantic Cache: `prompt_hash → response`, TTL. Anthropic `cache_control`. 50-80% Kostenreduktion | Mittel |
| **I4** | OpenTelemetry | JSONL | OTel Traces + Metrics + Logs. Export zu Grafana/Jaeger. JSONL bleibt als Fallback | Mittel |
| **I5** | Config-Validierung | Manuell | Pydantic v2 ODER `dataclasses` + `__post_init__`. JSON-Schema-Export für Settings-Tab | Klein |
| **I6** | Event-Sourcing | State verteilt (Labels, Dateien, Resume-JSON) | Workflow-State aus Event-Stream rekonstruierbar. `WorkflowProjection` baut Timeline | Hoch |
| **I7** | Code-Sandbox | `py_compile` + `ast.parse` | WASM-Sandbox (`wasmtime-py`/`pyodide`). LLM-Code in Sandbox vor Branch. Eliminiert E7 | Hoch (v3) |
| **I8** | Config-as-Code | `agent.json` manuell editiert | `agent.json` in Git. Dashboard-Änderung = auto-commit. Drift-Detection | Klein |
| **I9** | Webhook-first | Polling (30s-Intervall) | Webhook-first + Polling als Heartbeat-Fallback. Reduziert API-Calls auf ~0/Zyklus | Mittel |
| **I10** | Multi-Model-Ensemble | Ein Modell pro Task | Zwei Modelle parallel, Ergebnisse vergleichen. Divergenz → Human Review. Premium-Feature | Hoch |
| **I11** | DI-Container | Lazy-Imports (`_get_gitea()`, `_get_project()`) | Expliziter DI im Bootstrap. Constructor-Injection. Keine globalen Variablen | Mittel |

---

## Durchgang 6: Dashboard & Settings-Tab

### J. Dashboard-Erweiterungen

| # | Thema | Status | Handlungsbedarf |
|---|-------|--------|-----------------|
| **J1** | **Settings-Tab** | ❌ | REST-API `GET/PUT /api/settings/{section}`. Validierung per Schema. `ConfigChanged`-Events |
| **J2** | **Provider-Status** | ❌ | Live-Status pro Provider: healthy/degraded/down. Letzte Latenz, Error-Rate 24h |
| **J3** | **Workflow-Timeline** | ⚠️ 14-Schritt-Pipeline | Event-Sourced: jedes Event chronologisch. Klickbar. Kausale Kette via `causation_id` |
| **J4** | **Gate-Override-UI** | ❌ | Jedes Gate: `required`/`warn-only`/`disabled`. Änderung wird geaudited. Nur Admins (RBAC) |
| **J5** | **DLQ-Viewer** | ❌ | Fehlgeschlagene Commands. Retry/Discard-Button. Details |
| **J6** | **Cost-Dashboard** | ⚠️ Einzelkosten = Kern. Aggregation = Premium | Kern: Kosten pro Call. Premium: Charts, Trends, Forecast. Grenze dokumentieren |
| **J7** | **Realtime-Updates** | ❌ Statisch generiert | SSE/WebSocket: Bus-Events → Live-Update. Kein Page-Reload |
| **J8** | **Dark Mode** | ❌ | CSS `prefers-color-scheme` + Toggle |
| **J9** | **Export** | ❌ | Audit-Log, Score-History, Kosten als CSV/JSON. Für Compliance-Reports (AI Act Art. 11) |
| **J10** | **Multi-Projekt-Dashboard** | ❌ | Wenn Benutzersystem: alle Projekte eines Users. Projekt-Switcher. Aggregierte Kosten |

---

## Vergessene v1-Funktionen (nicht in v2-Architektur abgebildet)

### K. Funktionen die in v2-Datei-Mapping fehlen oder unterspezifiziert sind

| # | v1-Funktion | Wo in v1 | v2-Mapping | Problem |
|---|------------|----------|------------|---------|
| **K1** | `_strip_html()` — 4-fach dupliziert | `agent_start.py`, `helpers.py`, `quality_pipeline.py`, `generate_tests.py` (jede mit eigenem try/except Import) | `core/types.py` | v2 muss sicherstellen dass EINE Implementierung existiert. Kein erneutes Duplizieren |
| **K2** | `_RESTART_PATTERNS` — Server-Datei-Erkennung | `commands/pr.py` Zeile 53 | Nicht in v2 | Muss nach `config/agent_eval.json → restart_patterns` migrieren. Kein Hardcode |
| **K3** | `_fix_label_consistency()` — Label-Reparatur mit 5 Regeln | `commands/auto.py` Zeile 85-240 | ✅ Watch-Slice | OK, aber: kein Retry-Limit pro Issue (Endlosschleife bei API-Fehler). v2 muss Cooldown pro Issue einbauen |
| **K4** | `_check_systematic_tag_failures()` — Auto-Improvement-Issues | `commands/watch.py` Zeile 110-180 | ⚠️ Im Watch-Slice | Nicht explizit in v2-Events. Braucht: `TagFailureDetected`-Event → optional `CreateImprovementIssueCommand` |
| **K5** | `_sync_closed_contexts()` — Workspace-Cleanup | `commands/watch.py` Zeile 183-210 | ⚠️ | Muss im Watch-Slice am Zyklusbeginn laufen. Event: `WorkspaceCleanupCompleted` |
| **K6** | `_auto_marker_exists()` — Deduplication für Auto-Issues | `commands/watch.py` Zeile 83-90 | ❌ | Muss in v2 über `IdempotencyMiddleware` gelöst werden: `idempotency_key: "auto_issue:{test_name}"` |
| **K7** | `_build_issue_context_silent()` — Night-Kontext-Build | `commands/watch.py` Zeile 55-80 | ❌ | Nicht erwähnt. Muss als `BuildContextCommand` im Implementation-Slice leben |
| **K8** | `_signal_handler` + `_shutdown_event` — Graceful Shutdown Watch | `commands/watch.py` Zeile 19-24 | ✅ v2 Graceful Shutdown | OK — aber v2 muss `threading.Event` für Watch-Loop beibehalten, nicht nur SIGTERM |
| **K9** | `cmd_fixup()` — Bugfix nach Feedback | `commands/fixup.py` | ⚠️ "Implementation-Slice" | Label-Prüfung (muss `in-progress` sein) als eigenes Gate oder Precondition |
| **K10** | `cmd_generate_tests()` mit `auto=True` (LLM) vs `auto=False` (Kontext) | `commands/generate_tests.py` | ⚠️ AC-Verification-Slice | Zwei Modi müssen als getrennte Commands modelliert sein: `GenerateTestContextCommand` vs `GenerateTestsViaLLMCommand` |
| **K11** | `check_skeleton_fresh()` — Skeleton-Staleness im Pre-commit + Doctor | `plugins/llm_config_guard.py` Zeile 148-175 | ⚠️ Health-Slice | Muss als `SkeletonStalenessCheck` im Startup + Watch-Zyklus laufen |
| **K12** | `LLM_CONFIG_FILES` — 8 IDE-Config-Dateien (Claude, Cursor, Cline, Copilot, Windsurf, Aider, Gemini CLI, OpenHands) | `llm_config_guard.py` Zeile 51-63 | ❌ | Nicht in v2 erwähnt. Muss im Security-Slice als `LLMConfigIntegrityCheck` leben |
| **K13** | `_TEMPLATE_DIR` + `_TEMPLATES` — Kanonische IDE-Config-Templates | `llm_config_guard.py` Zeile 66-77 | ❌ | Templates müssen in v2 unter `config/llm/ide/` bleiben und vom Security-Slice verwaltet werden |
| **K14** | `OptimizerResult` + Stagnations-Erkennung + Komplexitäts-Wachstum | `plugins/optimizer.py` | ⚠️ Code-Analysis-Slice | Stagnation = Score-History-Analyse. Komplexität = AST-Diff. Zwei getrennte Checks |
| **K15** | `Anomaly`-Dataclass + `_PATTERNS` (6 Anomalie-Muster) + `_SPIKE_THRESHOLD` | `plugins/log_anomaly.py` | ⚠️ Watch-Slice | Pattern-Liste muss konfigurierbar sein: `config/agent.json → watch.anomaly_patterns` |
| **K16** | `compact_python()`, `compact_code()`, `fit_to_budget()` — Token-Kompaktierung | `plugins/context_compactor.py` | ⚠️ Context-Slice | Nicht explizit in v2 erwähnt. Muss im Context-Slice als Utility leben |
| **K17** | `_has_detailed_plan()` + `_get_user_feedback_comments()` — dupliziert in `agent_start.py` UND `helpers.py` | Beide Dateien | `core/types.py` oder Planning-Slice | v2 MUSS sicherstellen: genau EINE Implementierung. Kein erneutes Duplizieren |
| **K18** | `_validate_comment()` — Pflichtfeld-Prüfung für Kommentare | `agent_start.py` + `helpers.py` (dupliziert) | `core/types.py` | Dito |
| **K19** | Dashboard `/api/health` Endpoint mit Uptime, Score, LLM-Calls | `commands/dashboard_cmd.py` Zeile 78-100 | ❌ | Muss in v2 Dashboard-Slice als eigenständiger Health-Endpoint existieren |
| **K20** | `_server_start_time = time.time()` — Dashboard-Uptime-Tracking | `commands/dashboard_cmd.py` Zeile 14 | ❌ | In v2: `MetricsMiddleware` tracked Startzeit. Dashboard liest von dort |
| **K21** | `settings.register_reload_hook()` — Reload-Hook-System | `settings.py` Zeile 128 | ⚠️ | v2 ersetzt das durch `ConfigReloaded`-Event auf den Bus. Aber: Bridge-Phase muss beide Mechanismen unterstützen |

---

## Premium-Plugin Grenzziehung (Apache-Kern vs. Premium)

| Funktion | Apache-Kern (kostenlos) | Premium (kostenpflichtig) |
|----------|------------------------|--------------------------|
| LLM-Clients (Claude, DeepSeek, Gemini, Ollama, LMStudio, OpenRouter) | ✅ | |
| `complete()` mit Env-Fallback | ✅ | |
| OpenRouter-Pricing-Cache + `refresh_pricing()` | ✅ | |
| Einzelkosten pro Call (`estimate_cost()`) | ✅ | |
| Alle 14 Gates, Bus, Slices, Audit | ✅ | |
| **Task-basiertes Routing** (`routing.json`) | | ✅ |
| **Nacht-Routing** (günstigere Modelle nachts) | | ✅ |
| **Kosten-Aggregation** (by model/task/period, Charts) | | ✅ |
| **Token-Limit mit Auto-Resume** | | ✅ |
| **Dashboard LLM-Tab** (Kosten-Charts, Routing-Übersicht) | | ✅ |

**Architektur-Regel:** Kein `if premium:` im Kern. Premium registriert Handler auf dem Bus und überschreibt Default:
```
Bootstrap OHNE Premium: bus.register(LLMCallCommand, default_llm_handler)
Bootstrap MIT Premium:  bus.register(LLMCallCommand, routing_aware_llm_handler)
```

---

## Gesamtstatistik

| Durchgang | Kategorie | Findings |
|-----------|-----------|----------|
| 1 | Features & Provider (A) | 9 |
| 1 | Hardcoded Werte (B) | 22 |
| 1 | Strukturelle Verbesserungen (C) | 12 |
| 2 | Security (E) | 11 |
| 2 | EU AI Act & DSGVO (F) | 12 |
| 3 | Workflow-Robustheit (G) | 10 |
| 4 | Testing & CI (H) | 8 |
| 5 | 2026 Best Practice (I) | 11 |
| 6 | Dashboard (J) | 10 |
| — | Vergessene Funktionen (K) | 21 |
| **Gesamt** | | **126** |

---

## Durchgang 7: Weitere Findings (L, M, N, O)

### L. Plattform-Kompatibilität & Fehlende Error-Handling-Pfade

| # | Thema | v1-Status | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **L1** | **`fcntl` nur auf Unix** — `evaluation.py` nutzt `fcntl.flock()` für File-Locking | ❌ Bricht auf Windows | ❌ Nicht adressiert | `portalocker` oder `msvcrt`-Fallback. v2 muss plattformunabhängiges Locking in `core/types.py` bereitstellen |
| **L2** | **Blanket `except Exception:` überall** — 30+ Stellen (session.py, settings.py, helpers.py) schlucken Fehler still | ⚠️ Fehler unsichtbar | ❌ | Audit-Event bei jedem gefangenen Fehler. Kein stilles `pass` ohne Logging. v2-Coding-Standard: `except Exception as e: log.warning(...)` Minimum |
| **L3** | **Dashboard `time.sleep(60)` blockierend** | `dashboard_cmd.py` Z.566 | ❌ | Dashboard-Refresh-Intervall muss konfigurierbar sein: `config/dashboard.json → refresh_interval`. Nutze `threading.Event.wait(timeout)` statt `sleep` für Graceful Shutdown |
| **L4** | **Kein Timeout auf Audit-File-Write** | `audit.py` Z.472: `open(..., "a")` ohne Timeout | ❌ | Bei NFS/Network-Mounts kann `open()` hängen. Timeout + Fallback auf stderr |
| **L5** | **Session-JSON Race Condition** | `session.py`: Read-Modify-Write ohne Lock | ❌ | Bei `max_parallel > 1` können zwei Workflows gleichzeitig `session.json` korrumpieren. File-Lock nötig |
| **L6** | **Keine Health-Check-Endpoint-Authentifizierung** | Dashboard `/api/health` offen | ❌ | Auch read-only-Endpoints leaken Interna (Uptime, Score, LLM-Calls). Mindestens API-Key |

### M. Architektur-Inkonsistenzen zwischen Dokumenten

| # | Thema | Architektur-Dokument | Umsetzungsplan | Inkonsistenz |
|---|-------|---------------------|----------------|--------------|
| **M1** | **Middleware-Reihenfolge** | Sektion 2.6: Security → PromptGuard → Audit → Error → Metrics | Sektion 5.6: Idempotency → Security → PromptGuard → Audit → Error → Metrics | `IdempotencyMiddleware` fehlt in Sektion 2.6. Bootstrap (4.3) stimmt mit 5.6 überein, aber 2.6 ist inkonsistent |
| **M2** | **`IWorkflowDefinition` Widerspruch** | Sektion 4.2 sagt explizit "wird entfernt" | Umsetzungsplan erwähnt es nicht | OK, aber: `ports.py` in 0b.1 soll "alle IXxx ABCs" enthalten — Entwickler könnte es trotzdem anlegen |
| **M3** | **Semaphore-Release Terminal-Events unvollständig** | Architektur 5.4: `PRCreated, WorkflowBlocked, LLMUnavailable, PlanBlocked, WorkflowAborted` | Umsetzungsplan 5.4: identische Liste | Fehlt: `EvalFailed` (wenn kein Healing aktiv), `TokenLimitHit` (Workflow pausiert, Slot muss frei werden), `GateFailed` (alle Gates fehlgeschlagen, kein PR). Ohne diese Events: Semaphore-Leak |
| **M4** | **Phase 8.4 Reihenfolge vs. Abhängigkeiten** | 12 Slices in Phase 8.4 in "einfach nach komplex"-Reihenfolge | Keine Abhängigkeits-Analyse zwischen diesen 12 | `security/` muss vor `context/` kommen (HMAC-Signatur). `session/` muss vor `health/` (Checkpoint-Persistenz). Reihenfolge nicht korrekt |
| **M5** | **`chat_workflow.py` Mapping-Lücke** | Tabelle 7.2: `chat_workflow.py → slices/security/ + Workflow-Config` | Kein Chat-Workflow-Slice in der Slice-Auflistung (Kap. 7) | Chat-Workflow-Logik (Lock, HMAC, Steps) braucht eigene Handler im Security-Slice oder einen dedizierten Slice |

### N. Fehlende Events/Commands im Bus-Design

| # | Event/Command | Kontext | Warum nötig |
|---|--------------|---------|-------------|
| **N1** | `ConfigValidationFailed` | Startup, Hot-Reload | Pydantic-Validierungsfehler bei Config muss auditiert werden. Aktuell: Exception → `StartupBlocked` — aber bei Hot-Reload kein Startup |
| **N2** | `ProviderFallbackUsed` | LLM-Adapter | Wenn Primary-Provider ausfällt und Fallback greift. Für Cost-Tracking und Provider-Health essentiell |
| **N3** | `BranchCreated`, `BranchDeleted` | Implementation, Watch | Aktuell implizit. Für Audit-Trail und Stale-Branch-Detection als eigenständige Events nötig |
| **N4** | `SkeletonRebuilt` | Context-Slice | Skeleton-Rebuild muss auditiert werden (Timing, Dauer, Einträge). Fehlt in `events.py` |
| **N5** | `QualityRetry` | Quality-Slice | Zwischen `QualityFailed` und erneutem `QualityCheckCommand` fehlt ein Retry-Event für die Timeline |
| **N6** | `IssueSkipped` | Watch-Slice | Wenn Issue wegen Risikostufe übersprungen wird. Aktuell: stilles `continue` (Architektur 8.3). Muss auditiert werden |
| **N7** | `HookIntegrityFailed` | Health-Slice | SHA256-Mismatch des Pre-commit Hooks. Aktuell `StartupBlocked` — aber spezifischer Event für SIEM-Routing nötig |
| **N8** | `DashboardStarted` | Dashboard-Slice | Für Uptime-Tracking (K20) und Audit. Kein Event definiert wann Dashboard hochfährt |

### O. Weitere 2026 Best Practices & EU AI Act Lücken

| # | Thema | Quelle | Status | Handlungsbedarf |
|---|-------|--------|--------|-----------------|
| **O1** | **Kein Dependency-Pinning für LLM-SDKs** | Best Practice | ❌ | `anthropic`, `google-generativeai`, `openai` — Versionen müssen gepinnt sein. Breaking Changes in SDKs = stiller Ausfall |
| **O2** | **Kein Model-Deprecation-Handling** | Best Practice | ❌ | Provider deprecaten Modelle (z.B. `claude-2` → 404). `ModelDeprecated`-Event + Auto-Fallback auf nächstes Modell in `models.json` |
| **O3** | **AI Act Art. 15 — Genauigkeit & Robustheit** | EU AI Act | ❌ | Eval-Score-History als Robustness-Nachweis dokumentieren. Regression-Erkennung = Art. 15 Compliance |
| **O4** | **AI Act Art. 12 — Automatische Protokollierung** | EU AI Act | ⚠️ Audit existiert | Protokollierung muss "mindestens die Lebensdauer des Systems" aufbewahrt werden. `retention_days=10` (F5) verletzt das. Art. 12(2) verlangt Rückverfolgbarkeit pro Entscheidung |
| **O5** | **Kein Rollback für Config-Changes** | Best Practice | ❌ | Settings-Tab (J1) ohne Undo. `ConfigChanged`-Events mit `previous_value` für Rollback-Fähigkeit |
| **O6** | **Kein Rate-Limiting auf Bus-Commands** | Best Practice | ❌ | Ein fehlerhafter Webhook-Trigger könnte den Bus mit 1000 `PlanIssueCommand`s fluten. `RateLimitMiddleware` auf dem Bus nötig |
| **O7** | **Kein Canary-Deployment für LLM-Modell-Wechsel** | Best Practice | ❌ | Modellwechsel (z.B. Sonnet 3.5 → 4) ohne A/B-Test. Premium: Canary-Routing (10% Traffic auf neues Modell, Score vergleichen) |
| **O8** | **`correlation_id` Propagation zu externen Systemen** | Observability | ⚠️ Intern definiert | `correlation_id` muss in HTTP-Headern an LLM-Provider und SCM-API weitergegeben werden (`X-Correlation-ID`). Sonst: Tracing bricht an Systemgrenzen |
| **O9** | **Kein SBOM (Software Bill of Materials)** | EU AI Act Art. 11, Annex IV Nr. 2 | ❌ | `CycloneDX` oder `SPDX` SBOM generieren. Automatisiert in CI. Pflicht für High-Risk, empfohlen für Limited-Risk |
| **O10** | **Kein Input-Validierung auf Workflow-JSON** | Security | ⚠️ Pydantic erwähnt | `standard.json` mit unbekanntem Event-Namen → `UnhandledCommand`-Event (gut), aber: fehlende Validierung beim Laden könnte zu Runtime-Errors führen. Schema-Validierung beim Bootstrap |

---

## Durchgang 8: Code-Level Deep-Dive (P, Q, R)

### P. Security-Codeanalyse — bisher unentdeckte Lücken

| # | Thema | v1-Stelle | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **P1** | **Gemini API-Key in URL (Query-Parameter)** | `llm.py` Z.237: `url = f"...?key={self.api_key}"` | ❌ | API-Key wird in URL übergeben, nicht im Header. Wird in Server-Logs, Proxy-Logs und Monitoring geloggt. v2 `GeminiAdapter` muss `x-goog-api-key`-Header verwenden |
| **P2** | **Basic-Auth Token im Speicher als globale Variable** | `gitea_api.py` Z.57: `_AUTH = _make_auth(...)` — Base64-encoded Token als Modul-Global | ❌ | Token liegt unkodiert (Base64 ≠ Verschlüsselung) im Prozess-Speicher. Bei Core-Dump/Heap-Dump sichtbar. v2: Token nur on-demand aus `ISecretsProvider` holen, nicht cachen |
| **P3** | **`getpass.getpass()` Fallback im Produktivcode** | `gitea_api.py` Z.52: `prompt_fallback=False` (aktuell deaktiviert, aber Code vorhanden) | ❌ | Interaktiver Prompt in einer Library-Funktion. Wenn versehentlich `True`: Agent hängt auf stdin. v2: Entfernen. Config-Fehler → `ConfigValidationFailed`-Event |
| **P4** | **Healing nutzt `import anthropic` (SDK) statt HTTP** | `healing.py` Z.176: `_call_llm_claude()` importiert `anthropic`-SDK direkt | ❌ | Alle anderen Clients nutzen `urllib` (kein SDK-Zwang). Healing umgeht den LLM-Port komplett — kein Audit, kein CircuitBreaker, kein Cost-Tracking. v2: Healing MUSS über `ILLMProvider` gehen |
| **P5** | **`_apply_fixes()` liest Policy-JSON bei JEDEM Fix** | `healing.py` Z.316: `_eval_cfg.read_text()` + `json.loads()` in der Schleife | ❌ | Bei 5 Fixes = 5× File-Read + Parse. Kein Performance-Problem, aber: Race Condition wenn Config während Healing geändert wird. v2: Config einmal laden, per Injection |
| **P6** | **Kein Path-Traversal-Schutz bei DIFF-Tag** | `ac_verification.py` Z.170: `tag_arg in f for f in changed` — `tag_arg` aus Issue-Body | ⚠️ E7/E8 decken IMPORT/GREP ab | DIFF-Tag prüft nur Substring-Match. `tag_arg = "../../etc/passwd"` matched gegen jeden Diff mit `etc/passwd`. Whitelist: `tag_arg` darf keine `..` enthalten |
| **P7** | **`swap_label()` Add-before-Remove kann doppelte Labels erzeugen** | `gitea_api.py` Z.468: `add_label()` dann `remove_label()` — bei API-Fehler nach Add | ❌ | Wenn `remove_label()` fehlschlägt: Issue hat BEIDE Labels. `_fix_label_consistency()` repariert das, aber: in v2 als atomare SCM-Operation (`IVersionControl.swap_label`) oder mit Rollback |
| **P8** | **`hashlib.md5` für Temp-Branch-Namen** | `healing.py` Z.115 | ❌ | MD5 ist kryptografisch gebrochen. Hier nicht sicherheitskritisch (nur Branch-Name), aber: Code-Scanner flaggen es. v2: `hashlib.sha256` oder `secrets.token_hex(4)` |

### Q. API- & Datenfluss-Gaps

| # | Thema | v1-Stelle | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **Q1** | **Keine Pagination bei `get_issues()`** | `gitea_api.py` Z.165: `limit={settings.ISSUE_LIMIT}` — eine Seite, Rest abgeschnitten | ❌ | Projekte mit >50 offenen Issues verlieren Issues. v2 `IVersionControl.list_issues()` muss paginiert sein (Generator/async Iterator) |
| **Q2** | **`get_all_labels()` bei jedem `add_label()`/`remove_label()` Aufruf** | `gitea_api.py` Z.470, 490 — N API-Calls für N Label-Operationen | ❌ | N+1-Query-Problem. Bei 10 Issues mit je 2 Label-Swaps = 40 Label-API-Calls pro Zyklus. v2: Label-Registry cachen (per Zyklus oder mit TTL) |
| **Q3** | **v1 `LLMResponse` ≠ v2 `LLMResponse`** | v1: `text, provider, model, tokens_used, error, token_limit_hit, cost_usd`. v2: `text, input_tokens, output_tokens, cached_tokens, stop_reason, model_used, latency_ms` | ⚠️ In v2-Architektur definiert | Felder stimmen nicht überein: v1 hat `provider`, `ok`, `cost_usd` — v2 nicht. v1 fehlt `cached_tokens`, `latency_ms`, `stop_reason`. Bridge-Phase muss beide Formate bedienen. Migrations-Adapter nötig |
| **Q4** | **`_CycleCache` in `auto.py` hat keine TTL** | `auto.py` Z.30: Cache wird nur bei `invalidate()` geleert | ❌ | Bei langem Auto-Zyklus (30+ Min) kann der Cache stale werden wenn Issues extern geändert werden. v2: Cache mit TTL (z.B. 5 Min) oder Event-basierte Invalidierung |
| **Q5** | **Dashboard Auth-Header dupliziert** | `dashboard/data.py` Z.281: Baut eigenen `b64encode(bot_user:bot_token)` — dupliziert `gitea_api._make_auth()` | ❌ | Dashboard umgeht `gitea_api.py` komplett und baut eigenen Auth-Header. v2: Dashboard MUSS über `IVersionControl`-Port gehen |
| **Q6** | **`review.py` kennt keine Multi-File-Diffs** | `review.py` Z.40: `diff[:6000]` — schneidet Diff pauschal ab | ❌ B19 deckt den Hardcode ab | Aber: kein File-Splitting. Ein 6000-Char-Diff zeigt Datei A komplett und Datei B gar nicht. v2: Diff per Datei aufteilen, LLM pro Datei oder mit Zusammenfassung der restlichen Dateien |
| **Q7** | **Kein Retry bei LLM-Error in `complete()` (llm.py)** | `llm.py` Z.400ff: `complete()` hat keinen Retry-Mechanismus | ❌ | Einzelner 500er/Timeout = sofortiger Fehler. `CircuitBreakerAdapter` in v2 löst das auf Adapter-Ebene, aber: v1-Bridge-Phase hat keinen Schutz. Mindestens 1 Retry mit Backoff vor v2-Migration |

### R. LLM-Client-Inkonsistenzen

| # | Thema | Detail | Handlungsbedarf |
|---|-------|--------|-----------------|
| **R1** | **`complete(prompt: str)` vs v2 `complete(messages: list[dict])`** | v1: alle Clients nehmen `prompt: str`. v2-Port: `messages: list[dict]`. Inkompatibles Interface | Bridge-Adapter muss `str → [{"role": "user", "content": prompt}]` wrappen. Aber: Multi-Turn-Conversations (Healing-Retry mit Kontext) sind mit `str`-Interface unmöglich |
| **R2** | **ClaudeClient setzt KEINE `temperature`** | `llm.py` Z.112: Payload hat kein `temperature`-Feld (nutzt Anthropic-Default = 1.0). OpenAI/Gemini/Local: alle `0.2` | Inkonsistentes Verhalten zwischen Providern. Claude generiert mit höherer Varianz als alle anderen. v2: `temperature` als Pflichtfeld im `ILLMProvider.complete()` |
| **R3** | **LocalClient (Ollama) gibt keine Token-Counts zurück** | `llm.py` Z.295: `LLMResponse(text=text, provider="local", model=self.model)` — `tokens_used=0` | Cost-Tracking und Token-Budget-Berechnung blind für lokale Modelle. v2: Ollama `/api/generate` liefert `eval_count`/`prompt_eval_count` — muss extrahiert werden |
| **R4** | **Error-Handling gibt `LLMResponse(error=...)` statt Exception** | Alle Clients: `except Exception → return LLMResponse(error=str(exc))` | Fehler sind nicht-exzeptionell (kein Raise). Caller müssen `resp.ok` prüfen. Wenn vergessen: stiller Fehler. v2-Port sollte Exceptions raisen, `CircuitBreaker` fängt sie |
| **R5** | **`Gemini` hat keine `Gemini_API_ENABLED` in `_client_from_env()`** | `llm.py` Z.315-340: Fallback-Kette ist DeepSeek → Claude → LMStudio → Local. Kein Gemini | Gemini-Client existiert als Klasse (Z.230), aber wird vom Env-Fallback NIE gewählt. Nur über Premium-Routing (`routing.json`) erreichbar. v2: Gemini in Fallback-Kette aufnehmen oder dokumentieren warum nicht |
| **R6** | **`_http_post()` hat keine Response-Size-Limitierung** | `llm.py` Z.86: `resp.read()` liest unbegrenzt in den Speicher | Bei fehlerhafter LLM-API (z.B. Proxy gibt HTML-Fehlerseite zurück) kann `json.loads()` auf Megabytes crashen. v2: `resp.read(max_bytes)` mit sinnvolem Limit (z.B. 10MB) |

---

## Durchgang 9: Ergänzende Findings aus Code-Abgleich (S, T, U)

### S. Weitere Hardcoded Werte & Konfigurationslücken (Ergänzung zu B)

| # | Wert | Wo in v1 | v2-Status | Ziel-Config-Pfad |
|---|------|----------|-----------|-----------------|
| **S1** | `_MAX_FILE_SIZE_KB = 50` (Kontext-Dateien) | `context_loader.py` Z.107 | ❌ | `config/agent.json → context.max_file_size_kb` |
| **S2** | `_MAX_SKELETON_FILE_SIZE_KB = 20` | `context_loader.py` Z.108 | ❌ | `config/agent.json → context.max_skeleton_file_size_kb` |
| **S3** | `_EXCLUDE_DIRS_DEFAULT` — 20 Einträge hardcoded | `context_loader.py` Z.74-95 | ❌ | `config/agent.json → context.exclude_dirs` — Projekte mit anderen Ordnerstrukturen (z.B. `vendor/`, `dist/`) müssen anpassbar sein |
| **S4** | `_EXCLUDE_FILES` — Lock-Dateien hardcoded | `context_loader.py` Z.99ff | ❌ | `config/agent.json → context.exclude_files` |
| **S5** | `_MAX_LOG_SIZE_BYTES = 10_000_000` (10 MB Audit-Log-Rotation) | `plugins/audit.py` Z.313 | ❌ | `config/agent.json → logging.max_log_size_mb` |
| **S6** | `_KEYWORD_SEARCH_EXTENSIONS` — 7 Extensions hardcoded | `context_loader.py` Z.97 | ❌ | `config/agent.json → context.keyword_extensions` — TypeScript-Projekte bräuchten `.tsx`, `.jsx` |
| **S7** | `timeout_s=10.0` bei Sequence-Extraction | `context_loader.py` Z.509 | ❌ | `config/agent.json → context.sequence_timeout` |
| **S8** | `min_support: 0.9`, `min_count: 5` (Pattern-Miner Defaults) | `plugins/pattern_miner.py` Z.25-26 | ❌ | `config/agent.json → analysis.pattern_min_support`, `pattern_min_count` |
| **S9** | `_MIN_PARAMS_B = 7` (LLM-Quality Min-Parameter-Prüfung) | `plugins/llm_quality.py` Z.26 | ❌ | `config/agent.json → llm.min_local_model_params_b` |
| **S10** | `body[:2000]` — Issue-Body-Truncation in AC-Verification | `plugins/ac_verification.py` Z.363 | ❌ | `config/agent.json → ac.max_body_chars` |
| **S11** | `DASHBOARD_PORT = 8888` nur über `agent.json`, aber `timeout=5` für Dashboard-Health-Check hardcoded | `commands/dashboard_cmd.py` Z.137 | ❌ | `config/agent.json → dashboard.health_timeout` |
| **S12** | `body[:400]` — Issue-Body-Truncation in `save_plan_context()` | `commands/plan.py` Z.54 | ❌ | `config/agent.json → context.plan_body_max_chars` |
| **S13** | `LMStudioClient._BASE_URL = "http://localhost:1234/v1"` | `plugins/llm.py` Z.217 | ❌ | Zwar per `LMSTUDIO_URL` env-var überschreibbar, aber nicht in `agent.json`. v2: alle Provider-URLs in `config/llm/providers.json` |
| **S14** | `LocalClient` Default-URL `http://localhost:11434` + Default-Modell `llama3` | `plugins/llm.py` Z.349-350 | ❌ | `config/agent.json → llm.local_url`, `llm.local_model` (konsistent mit anderen Providern) |

### T. Vergessene v1-Funktionen & Prozesslücken (Ergänzung zu K)

| # | v1-Funktion / Prozess | Wo in v1 | v2-Mapping | Problem |
|---|----------------------|----------|------------|---------|
| **T1** | `restart_manager.py` — Granulares Service-Neustart-Management (auto/manual per Service, Issue-Erstellung bei manuellen Services) | `plugins/restart_manager.py` (264 Zeilen) | ❌ Nicht in v2 erwähnt | Komplettes Modul fehlt im v2-Slice-Mapping. Muss im Evaluation-Slice oder als eigener Service-Management-Slice leben |
| **T2** | `pattern_miner.py` — Bigram-Muster-Lernen aus Call-Sequenzen | `plugins/pattern_miner.py` (95 Zeilen) | ❌ | Wird von `sequence_validator.py` konsumiert. Muss als Utility im Quality-Slice leben |
| **T3** | `sequence_extractor.py` + `sequence_validator.py` — Call-Sequenz-Analyse | `plugins/` | ⚠️ Quality-Slice | Extractor + Validator + Miner = 3 Module die zusammenhängen. v2 muss deren Interaktion klären |
| **T4** | `llm_quality.py` — Param-Size-Check + empirische Plan-Validierung | `plugins/llm_quality.py` (236 Zeilen) | ❌ | Nicht im v2-Slice-Mapping. Muss im LLM-Slice als Pre/Post-Middleware oder Quality-Check leben |
| **T5** | `llm_wizard.py` — Interaktiver CLI-Wizard für LLM-Konfiguration | `plugins/llm_wizard.py` (250 Zeilen) | ❌ | Nicht in v2 erwähnt. Wird durch Settings-Tab (J1) teilweise ersetzt, aber CLI-Variante bleibt für Headless-Server nötig |
| **T6** | `setup_wizard.py` — Interaktiver Setup für `.env` + `agent.json` | `plugins/setup_wizard.py` | ❌ | Fehlt komplett in v2. Onboarding für neue Nutzer. Muss als CLI-Command erhalten bleiben |
| **T7** | `_apply_auto_approve()` — `.claude/settings.local.json` Generierung | `commands/auto.py` Z.74-96 | ❌ | Schreibt Claude-Code-spezifische Permissions. Nicht in v2 erwähnt. Muss als IDE-Integration-Feature erhalten bleiben |
| **T8** | `_FEATURE_REGISTRY` — 22 Feature-Flags mit Beschreibung + Default | `settings.py` Z.532-556 | ⚠️ | v2-Architektur erwähnt Feature-Flags nicht explizit. Migration muss sicherstellen dass alle 22 Flags in v2 konfigurierbar bleiben |
| **T9** | `_load_docs_check_config()` + `DOCS_CHECK_CONFIG` — Docs-Prüfung mit Schwellwert + Excludes | `settings.py` Z.600-630 | ❌ | Nicht in v2-Architektur. Muss als Quality-Check im Quality-Slice leben |
| **T10** | `COMMENT_REQUIRED_FIELDS` — Pflichtfelder pro Kommentar-Typ (4 Typen) | `settings.py` Z.647-656 | ❌ | Konfigurierbare Kommentar-Validierung fehlt in v2 komplett |
| **T11** | `_server_start_time()` — Server-Start-Zeitpunkt aus Logfile extrahieren | `commands/pr.py` Z.93ff | ❌ | Eval braucht den Server-Start-Zeitpunkt. Nicht im v2-Evaluation-Slice spezifiziert |
| **T12** | `_CycleCache.get_issue(number)` — Einzelnes Issue aus Cache ODER API | `commands/auto.py` Z.52-56 | ❌ | v2 Watch-Slice braucht analogen Cache mit Einzel-Lookup-Fallback |
| **T13** | `_failed_issues: set[int]` — Modul-globale Fehlerliste für Auto-Zyklus | `commands/auto.py` Z.23 | ❌ | State-Management für fehlgeschlagene Issues fehlt in v2. Muss als `WorkflowState` im Watch-Slice persistiert werden, nicht als globale Variable |
| **T14** | GitHub-Mirror-Support (`GITHUB_TOKEN`, `GITHUB_REPO`) | `dashboard/data.py` Z.1401-1402 | ❌ | Dashboard kennt GitHub-Config, aber kein SCM-Adapter für GitHub in v2. `IVersionControl`-Port braucht `GitHubAdapter` |

### U. Weitere Error-Handling & Robustheits-Gaps

| # | Thema | v1-Stelle | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **U1** | **`_strip_html()` 5-fach dupliziert (nicht 4-fach wie in K1)** | `agent_start.py`, `helpers.py`, `context_loader.py`, `ac_verification.py` (Fallback), `quality_pipeline.py` (Fallback) — plus Delegierer in `generate_tests.py` | ❌ | K1 sagt 4-fach, tatsächlich 5 eigenständige Implementierungen + 1 Delegierer. Schlimmer als dokumentiert |
| **U2** | **`settings.reload()` hat blanket `except Exception: pass` in Hooks** | `settings.py` Z.260-262 | ❌ | Wenn ein Reload-Hook fehlschlägt: stiller Fehler. Modul arbeitet mit veralteter Config. Mindestens `log.warning()` |
| **U3** | **`_validate_agent_cfg()` prüft nur Top-Level-Keys** | `settings.py` Z.101-105 | ❌ | Typos in Nested-Keys (`labels.redy` statt `labels.ready`) werden nicht erkannt. v2: Pydantic-Schema-Validierung auf allen Ebenen |
| **U4** | **`_env()` liest `.env`-Datei bei JEDEM Aufruf** | `settings.py` Z.21-36 | ❌ | Bei 50+ `_env()`-Aufrufen beim Import = 50× File-Read + Parse. Kein Caching. Performance bei Netzwerk-Mounts problematisch |
| **U5** | **`_load_features()` Fallback auf `project.json` (Legacy)** | `settings.py` Z.570-590 | ❌ | Legacy-Pfad wird nie aufgeräumt. v2 muss `project.json`-Support dokumentiert entfernen oder bewusst beibehalten |
| **U6** | **`auto.py` Poll-Loop hat kein `settings.reload()` für `poll_interval`/`poll_timeout`** | `commands/auto.py` Z.558-559 | ❌ | Diese Werte werden einmal gelesen, `settings.reload()` in der Schleife aktualisiert sie nicht weil sie lokale Variablen sind |
| **U7** | **`auto.py` `finally`-Block macht `git checkout -- .` + `git checkout main`** | `commands/auto.py` Z.630-637 | ❌ | Bei uncommitted Changes in einem anderen Branch: stille Datenverluste. Sollte `git stash` nutzen (vgl. G1) |
| **U8** | **Kein Timeout auf `gitea.get_comments()`-Calls in Auto-Loop** | `commands/auto.py` Z.548-551 | ❌ | Für jedes wartende Issue werden Kommentare geladen. Bei Gitea-Latenz (500ms+) und 20 Issues: 10s+ Blockade pro Zyklus |
| **U9** | **`_client_from_env()` liest `.env` erneut statt `settings`-Modul zu nutzen** | `plugins/llm.py` Z.310-320 | ❌ | Doppelte `.env`-Parsing-Logik. Kann zu Inkonsistenzen führen wenn `settings.reload()` aufgerufen wurde aber `llm.py` die Datei direkt liest |
| **U10** | **`complete()` loggt `base_url` aus `routing.json` bei jedem Call** | `plugins/llm.py` Z.415-425 | ❌ | Liest `routing.json` bei JEDEM LLM-Call (analog P5). File-Read in Hot-Path. v2: einmal laden, Event-basiert invalidieren |

---

## Aktualisierte Gesamtstatistik

| Durchgang | Kategorie | Findings |
|-----------|-----------|----------|
| 1 | Features & Provider (A) | 9 |
| 1 | Hardcoded Werte (B) | 22 |
| 1 | Strukturelle Verbesserungen (C) | 12 |
| 2 | Security (E) | 11 |
| 2 | EU AI Act & DSGVO (F) | 12 |
| 3 | Workflow-Robustheit (G) | 10 |
| 4 | Testing & CI (H) | 8 |
| 5 | 2026 Best Practice (I) | 11 |
| 6 | Dashboard (J) | 10 |
| — | Vergessene Funktionen (K) | 21 |
| 7 | Plattform & Error-Handling (L) | 6 |
| 7 | Architektur-Inkonsistenzen (M) | 5 |
| 7 | Fehlende Events/Commands (N) | 8 |
| 7 | Weitere Best Practices & AI Act (O) | 10 |
| 8 | Security-Codeanalyse (P) | 8 |
| 8 | API/Datenfluss-Gaps (Q) | 7 |
| 8 | LLM-Client-Inkonsistenzen (R) | 6 |
| 9 | Hardcoded Werte Ergänzung (S) | 14 |
| 9 | Vergessene Funktionen Ergänzung (T) | 14 |
| 9 | Error-Handling & Robustheit (U) | 10 |
| 10 | Packaging & Dependency (V) | 8 |
| 10 | Fehlende TLS/SSL & Netzwerk-Härtung (W) | 7 |
| 10 | Logging & Observability Gaps (X) | 6 |
| 10 | Windows/Cross-Platform Ergänzung (Y) | 5 |
| 10 | 2026 Goldstandard Ergänzung (Z) | 8 |
| **Gesamt** | | **248** |

---

## Durchgang 10: Packaging, Netzwerk, Logging, Cross-Platform, 2026 Goldstandard (V, W, X, Y, Z)

### V. Packaging & Dependency-Management — komplett fehlend

| # | Thema | v1-Status | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **V1** | **Kein `requirements.txt` / `pyproject.toml`** | ❌ Weder `requirements.txt` noch `pyproject.toml` im Repository | ❌ Nicht in v2 adressiert | **KRITISCH für Reproduzierbarkeit:** Ohne Dependency-Datei ist kein `pip install` reproduzierbar. v2 muss `pyproject.toml` mit gepinnten Versionen enthalten. Abhängigkeiten: `jinja2`, `anthropic` (optional), `pydantic` (v2-neu), `tiktoken` (geplant) |
| **V2** | **Keine `__init__.py` im Root** — S.A.M.U.E.L. ist kein installierbares Paket | ❌ Lose Skripte | ⚠️ v2 plant `samuel/` Package | v2-`pyproject.toml` muss `samuel` als installierbares Package definieren (`pip install -e .`). CLI-Entry-Point: `[project.scripts] samuel = "samuel.cli:main"` |
| **V3** | **Kein Lockfile** | ❌ | ❌ | `pip-compile` (pip-tools) oder `uv lock` für deterministische Builds. Ohne Lockfile: CI und Produktion können unterschiedliche Versionen installieren |
| **V4** | **`jinja2` Import mit manuellem try/except** | `agent_start.py` Z.90-92: `try: import jinja2 except: print("pip install jinja2")` | ❌ | Optional-Dependencies in `pyproject.toml`: `[project.optional-dependencies] dashboard = ["jinja2>=3.1"]`. Kein `try/except import` im Produktivcode |
| **V5** | **Kein Python-Mindestversion deklariert** | ❌ Code nutzt `match/case` (3.10+), `X | Y` Union-Syntax (3.10+), aber nirgends dokumentiert | ❌ | `pyproject.toml → requires-python = ">=3.10"`. Startup-Check: `sys.version_info >= (3, 10)` |
| **V6** | **`anthropic`-SDK direkt importiert in Healing** (P4 ergänzend) | `healing.py` Z.176 | ❌ | Zusätzlich: kein `ImportError`-Handling wenn `anthropic` nicht installiert. Agent crasht beim ersten Heal-Versuch wenn SDK fehlt |
| **V7** | **Kein `py.typed` Marker** | ❌ | ❌ | PEP 561: `samuel/py.typed` für Type-Checker-Kompatibilität. 2026 Standard für Python-Libraries |
| **V8** | **Keine `MANIFEST.in` / Build-Konfiguration** | ❌ | ❌ | Config-Dateien (`config/`, `dashboard/templates/`, `dashboard/static/`) müssen im Package enthalten sein. `pyproject.toml → [tool.setuptools.package-data]` |

### W. TLS/SSL & Netzwerk-Härtung

| # | Thema | v1-Status | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **W1** | **Keine TLS-Verifizierung konfigurierbar** | Alle HTTP-Calls nutzen `urllib.request.urlopen()` ohne explizites SSL-Context-Handling | ❌ | Für Self-Hosted Gitea mit Self-Signed Certs: `config/agent.json → scm.tls_verify: true`, `scm.ca_bundle: "/path/to/ca.pem"`. Default: Verify ON |
| **W2** | **Dashboard läuft auf HTTP** | `dashboard_cmd.py` startet reinen HTTP-Server | ❌ | Mindestens Dokumentation: "Hinter Reverse Proxy mit TLS betreiben". Oder: optionales TLS via `config/dashboard.json → tls.cert_path`, `tls.key_path` |
| **W3** | **Gitea-API-Calls ohne Connection-Pooling** | Jeder Call öffnet neue TCP-Verbindung | ❌ | `urllib3.PoolManager` oder `requests.Session` für Connection-Reuse. Bei 40+ API-Calls/Zyklus (Q2) relevant |
| **W4** | **Kein User-Agent-Header** | LLM-Calls und Gitea-Calls senden keinen `User-Agent` | ❌ | `User-Agent: S.A.M.U.E.L./2.0 (https://github.com/...)`. Pflicht für API-Best-Practices. Manche Provider rate-limiten Calls ohne User-Agent strenger |
| **W5** | **Keine Proxy-Unterstützung** | ❌ `urllib` nutzt System-Proxy automatisch, aber nicht explizit konfigurierbar | ❌ | Enterprise-Umgebungen: `config/agent.json → network.http_proxy`, `network.https_proxy`, `network.no_proxy` |
| **W6** | **Healing-LLM-URL ist HTTP** (nicht HTTPS) | `healing.py` Z.34: `http://localhost:11434` | ❌ | Lokale Ollama-Calls über HTTP sind OK, aber: Default-URLs sollten dokumentiert warnen wenn über Netzwerk (nicht localhost) genutzt |
| **W7** | **Kein DNS-Caching** | Jeder API-Call löst DNS auf | ❌ | Bei instabilen DNS-Servern: `socket.setdefaulttimeout()` + DNS-Cache-Middleware oder explizites Caching. Niedrige Prio, aber in Air-Gapped-Umgebungen relevant |

### X. Logging & Observability Gaps (Ergänzung zu C10/I4)

| # | Thema | v1-Status | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **X1** | **Kein strukturiertes Logging** — `print()` an 100+ Stellen statt Logger | ⚠️ Mischung aus `print()` und `log.info()` | ❌ | v2 muss ALLE `print()`-Ausgaben durch Logger ersetzen. `print()` nur in CLI-Layer (`samuel/cli.py`). Strukturiertes JSON-Logging für maschinelle Auswertung |
| **X2** | **Log-Rotation nur für Audit, nicht für Agent-Log** | `audit.py` hat `_MAX_LOG_SIZE_BYTES`. `gitea-agent.log` hat keine Rotation | ❌ | `logging.handlers.RotatingFileHandler` mit konfigurierbarer Größe. Ohne Rotation: Log füllt Disk nach Wochen im Watch-Modus |
| **X3** | **Kein Request-ID in Gitea-API-Calls** | ❌ | ❌ | Gitea gibt `X-Request-Id` zurück. Muss geloggt werden für Support-Anfragen. v2: `correlation_id` als `X-Request-Id`-Quelle an Gitea senden |
| **X4** | **Keine Metriken für Gitea-API-Latenz** | ❌ | ⚠️ MetricsMiddleware existiert, aber nur für Bus-Commands | SCM-Adapter muss Latenz pro Call messen und als Metrik bereitstellen. Für Provider-Health (J2) essentiell |
| **X5** | **`--doctor` Ergebnisse nicht maschinell auswertbar** | Output ist Freitext an stdout | ❌ | `--doctor --json` für CI-Integration. JSON-Output mit `{checks: [{name, passed, message}]}`. Für Health-Endpoint (K19) wiederverwendbar |
| **X6** | **Kein Log-Sampling bei hohem Volumen** | ❌ | ❌ | Watch-Modus im 30s-Takt über Wochen: Log wächst unkontrolliert. Sampling für repetitive Events (`IssueSkipped`, `LabelCorrected`) nach N Wiederholungen |

### Y. Windows/Cross-Platform (Ergänzung zu L1)

| # | Thema | v1-Status | v2-Status | Handlungsbedarf |
|---|-------|-----------|-----------|-----------------|
| **Y1** | **`signal.SIGTERM` nicht auf Windows verfügbar** | `watch.py` Z.686: `signal.signal(signal.SIGTERM, ...)` | ❌ L1 deckt nur `fcntl` ab | Windows hat kein `SIGTERM`. Nur `SIGINT` (Ctrl+C) und `SIGBREAK`. v2 muss `if sys.platform != 'win32':` Guard für `SIGTERM` setzen |
| **Y2** | **Shell-Commands mit Unix-Syntax** | `subprocess.run(["git", ...])` funktioniert, aber Skripte wie `scripts/*.sh` sind Bash-only | ❌ | v2 muss alle Shell-Abhängigkeiten dokumentieren. Alternative: PowerShell-Varianten für Windows |
| **Y3** | **`.env`-Dateiberechtigungen 600/640 nur auf Unix** | `agent_self_check.py` Schicht 4: `.env`-Permissions-Check | ❌ | Windows hat kein `chmod 600`. v2: `os.name == 'nt'` Guard. Windows-Alternative: ACL-Prüfung via `icacls` |
| **Y4** | **`atexit.register(lambda: _lock_path.unlink())` Race auf Windows** | `agent_start.py` Z.1139-1140 | ❌ | Windows hält File-Locks strenger. `unlink()` auf gelockte Datei schlägt fehl. v2: `try/except PermissionError` |
| **Y5** | **PID-basiertes Locking (`os.kill(pid, 0)`)** | `commands/doctor.py` Z.158 | ❌ | `os.kill(pid, 0)` funktioniert anders auf Windows (kein Signal 0). v2: `psutil.pid_exists()` oder `tasklist`-Fallback |

### Z. 2026 Goldstandard — weitere Best Practices

| # | Thema | Aktuell | 2026 Best Practice | Aufwand |
|---|-------|---------|-------------------|---------|
| **Z1** | **Kein `pre-commit` Framework** | Eigener Hook in `.git/hooks/pre-commit` | `pre-commit` Framework (pre-commit.com) mit `.pre-commit-config.yaml`. Standard für Python-Projekte 2026. Ermöglicht: ruff, mypy, bandit als Hook. Kompatibel mit bestehendem Custom-Hook | Klein |
| **Z2** | **Kein Linter/Formatter konfiguriert** | ❌ Kein `ruff`, `black`, `flake8` | `ruff` als All-in-One (Linter + Formatter). `pyproject.toml → [tool.ruff]`. 100x schneller als flake8+isort+black. 2026 De-facto-Standard | Klein |
| **Z3** | **Kein Type-Checking** | ❌ Keine Type-Annotations erzwungen | `mypy --strict` oder `pyright` in CI. `pyproject.toml → [tool.mypy]`. v2-Code MUSS vollständig annotiert sein. v1-Bridge-Code: `mypy --follow-imports=silent` | Mittel |
| **Z4** | **Kein Dependency-Scanning in CI** | ⚠️ `dep_checker.py` existiert für Zielprojekte, nicht für S.A.M.U.E.L. selbst | `pip-audit` / `safety` in CI für eigene Dependencies. S.A.M.U.E.L. prüft andere Projekte, aber nicht sich selbst | Klein |
| **Z5** | **Kein `SECURITY.md`** | ❌ | Pflicht für Open-Source 2026: Vulnerability-Disclosure-Policy, unterstützte Versionen, Kontakt für Security-Reports. GitHub/Gitea zeigen es prominent | Klein |
| **Z6** | **Kein `CONTRIBUTING.md`** | ❌ | Community-Standard für Apache-2.0-Projekte: Wie beiträgt man? Welche Coding-Standards? Wie werden PRs gereviewed? | Klein |
| **Z7** | **Kein Container-Image / Dockerfile** | ❌ | `Dockerfile` für reproduzierbare Deployments. Multi-Stage-Build: Build-Stage mit Dev-Dependencies, Runtime-Stage minimal. `docker compose` für Gitea + S.A.M.U.E.L. + Dashboard | Mittel |
| **Z8** | **Keine Healthcheck-Probes für Container** | ❌ | `HEALTHCHECK` in Dockerfile. Kubernetes: `livenessProbe` + `readinessProbe` auf `/api/health`. Auch für `systemd` Service: `ExecStartPost` Health-Check | Klein |

---

## Top-15 Prioritäten (aktualisiert)

| Prio | Finding | Grund |
|------|---------|-------|
| 1 | **E7** Code-Injection via AC-Tag | Sicherheitslücke, ausnutzbar über Issue-Body |
| 2 | **F3** PII-Scrubbing vor LLM-Calls | DSGVO-Pflicht |
| 3 | **V1** Kein `pyproject.toml` / `requirements.txt` | Nicht reproduzierbar installierbar, blockiert jeden Contributor |
| 4 | **M3** Semaphore-Release Terminal-Events unvollständig | Semaphore-Leak blockiert Agent dauerhaft |
| 5 | **F12** Drittland-Transfer-Warnung | DSGVO Art. 44 |
| 6 | **L1** `fcntl` nur auf Unix | Agent bricht auf Windows, Plattform des Nutzers |
| 7 | **J1** Settings-Tab | Ohne das = jede Änderung per SSH |
| 8 | **B14** Context-Window pro Modell | Abgeschnittene Responses, Token-Verschwendung |
| 9 | **A1/A2/A3** OpenRouter + Gemini als Adapter | 300+ Modelle, bereits in v1 genutzt, fehlen in v2-Adapter-Liste |
| 10 | **G6** Dead-Letter-Queue | Fehlgeschlagene Commands gehen leise verloren |
| 11 | **Z2** Kein Linter/Formatter (ruff) | Code-Qualität nicht automatisch durchgesetzt |
| 12 | **F2** KI-Attribution Pflicht | AI Act Art. 50 |
| 13 | **O6** Rate-Limiting auf Bus-Commands | Webhook-Flooding kann Agent lahmlegen |
| 14 | **L2** Blanket `except Exception` | 30+ stille Fehler, Debugging unmöglich |
| 15 | **I2** Structured Output | Größter Qualitätssprung bei Patches |
