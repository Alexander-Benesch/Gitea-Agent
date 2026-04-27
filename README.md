# S.A.M.U.E.L.

### Sicheres Autonomes Mehrschichtiges Ueberwachungs- und Entwicklungs-Logiksystem

S.A.M.U.E.L. ist ein Zero-Trust-Framework, das LLM-gestuetzte Softwareentwicklung
kontrolliert, ueberwacht und auditierbar macht. Das Framework orchestriert LLMs als
austauschbare, nicht vertrauenswuerdige Worker und erzwingt technische Schranken die
kein Prompt umgehen kann.

## Ueberblick

S.A.M.U.E.L. nimmt ein Gitea-Issue entgegen und fuehrt es autonom durch einen
konfigurierbaren Workflow: **Plan erstellen** → **Code generieren** → **Ergebnis bewerten**
→ **Pull Request anlegen**. Jeder Schritt wird durch Gates, Budgets und Audit-Trails
abgesichert.

```
Issue (Gitea)
  │
  ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Planning   │───▶│Implementation│───▶│  Evaluation  │───▶│   PR Gates   │
│  LLM → Plan  │    │ LLM → Patches│    │ Score → Pass │    │ 14 Checks →  │
│  validate()  │    │  parse/apply  │    │   /Fail/Heal │    │   PR/Block   │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

## Schnellstart

### Voraussetzungen

- Python >= 3.10
- Gitea-Instanz mit API-Token
- LLM-Provider (Ollama, DeepSeek, Claude oder LM Studio)

### Installation

```bash
git clone http://192.168.1.60:3001/Alexmistrator/S.A.M.U.E.L.git
cd S.A.M.U.E.L
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Konfiguration

```bash
cp .env.example .env
```

`.env` anpassen:

```env
SCM_PROVIDER=gitea
SCM_URL=http://192.168.1.60:3001
SCM_TOKEN=dein-gitea-token
SCM_REPO=owner/repo
SCM_USER=dein-username
OLLAMA_URL=http://localhost:11434
```

### Starten

```bash
# Health-Check
python -m samuel health

# Dashboard (Web-UI + REST-API auf Port 7777)
python -m samuel dashboard

# Einzelnes Issue bearbeiten
python -m samuel run 42

# Watch-Modus: Issues automatisch abarbeiten
python -m samuel watch

# Einmal scannen, dann beenden
python -m samuel watch --once
```

### Als systemd-Service

```bash
sudo cp samuel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now samuel
```

## Architektur

Event-Driven Monolith mit Vertical Slices. Kein Slice importiert einen anderen —
Kommunikation laeuft ausschliesslich ueber den zentralen Bus via Events und Commands.

```
samuel/
├── core/               Shared Kernel
│   ├── bus.py            Event-Bus + 6 Middlewares
│   ├── bootstrap.py      12-Step Startup-Sequenz
│   ├── commands.py       15 Command-Typen + Registry
│   ├── events.py         30 Event-Typen
│   ├── workflow.py       WorkflowEngine (JSON-basiert)
│   ├── config.py         Pydantic-validierte Config
│   ├── ports.py          16 Interface-Definitionen
│   ├── types.py          Domain-Typen (Issue, PR, LLMResponse, ...)
│   ├── errors.py         Error-Hierarchie
│   ├── http_client.py    HTTP-Client-Abstraktion
│   └── logging.py        Logging-Setup
├── adapters/           Externe Systeme
│   ├── api/              REST-API + Webhook-Ingress
│   ├── audit/            JSONL-Sink + Async-Buffer
│   ├── auth/             Token-Authentifizierung
│   ├── gitea/            Gitea-SCM-Adapter
│   ├── github/           GitHub-SCM-Adapter + App-Auth
│   ├── llm/              LLM-Factory (Ollama, DeepSeek, Claude, LM Studio)
│   ├── notifications/    Slack, Teams, Generic Webhooks
│   ├── quality/          IQualityCheck-Registry + Checks
│   ├── secrets/          Env-Secrets-Provider
│   └── skeleton/         Code-Skeleton-Builder
├── slices/             Feature Slices (21 Stueck)
│   ├── ac_verification/  Akzeptanzkriterien pruefen (DIFF, GREP, IMPORT, ...)
│   ├── architecture/     Architektur-Analyse
│   ├── audit_trail/      Audit-Trail-Management
│   ├── changelog/        Changelog-Generierung aus Kategorien
│   ├── code_analysis/    Code-Analyse
│   ├── context/          Code-Skeleton + File-Slices fuer LLM-Kontext
│   ├── dashboard/        Status, Metriken, Health-Aggregation
│   ├── evaluation/       Gewichtetes Scoring mit History
│   ├── healing/          Fehler-Recovery via LLM mit Budget-Kontrolle
│   ├── health/           System-Health-Checks (Python, Config, SCM, LLM)
│   ├── implementation/   Plan → Code via Multi-Round LLM-Loop
│   ├── planning/         Issue → LLM-Plan mit Validierung + Retry
│   ├── pr_gates/         14 Gates (Branch, Scope, Secrets, Eval, ...)
│   ├── privacy/          PII-Scrubber + DSGVO + AI-Act
│   ├── quality/          Plugin-basierte Quality-Checks
│   ├── review/           LLM-basiertes Code-Review
│   ├── security/         Secret-Scan, Prompt-Injection, Command-Safety
│   ├── sequence/         Event-Sequenz-Tracking + Muster-Analyse
│   ├── session/          Token-/Zeit-Budget + Workflow-Checkpoints
│   ├── setup/            Verzeichnisse + Env-Var-Validierung
│   └── watch/            Issue-Polling mit Semaphore-Concurrency
├── server.py           HTTP-Server (Dashboard + REST + Webhooks)
├── cli.py              CLI (watch, run, health, dashboard)
└── __main__.py         Entry-Point
```

## Middleware-Kette

Jeder Command/Event durchlaeuft 6 Middlewares in fester Reihenfolge:

1. **IdempotencyMiddleware** — Deduplizierung via TTL-basiertem Store
2. **SecurityMiddleware** — Blockiert verbotene Muster
3. **PromptGuardMiddleware** — Erzwingt Guard-Marker in LLM-Prompts
4. **AuditMiddleware** — Protokolliert alle Nachrichten mit Correlation-ID
5. **ErrorMiddleware** — Exception-Handling, publiziert WorkflowAborted
6. **MetricsMiddleware** — Zaehlt Aufrufe, Fehler und Latenz pro Typ

## Workflows

Workflows sind JSON-Dateien in `config/workflows/`. Jeder Step mappt ein Event auf einen Command:

| Workflow | Beschreibung | Parallelitaet |
|----------|-------------|---------------|
| `standard` | Issue → Plan → Implement → Eval → PR | 1 |
| `watch` | Wie standard, mit Polling-Loop | 2 |
| `autonomous` | Vollautonomer Betrieb | 1 |
| `chat` | Interaktiver Modus | 1 |
| `night` | Nacht-Batch-Verarbeitung | 3 |
| `patch` | Nur Patch-Anwendung | 1 |
| `self` | Self-Mode (Agent arbeitet auf sich selbst) | 1 |

## PR Gates

14 Gates pruefen jeden PR vor dem Erstellen. Konfigurierbar in `config/gates.json`:

| Gate | Pruefung | Typ |
|------|----------|-----|
| 1 | Branch nicht main/master | Required |
| 2 | Plan-Kommentar vorhanden (>20 Zeichen) | Required |
| 3 | Agent-Metadaten im Plan | Required |
| 7 | Keine .env/secrets/credentials im Diff | Required |
| 11 | Akzeptanzkriterien vorhanden | Required |
| 13b | Loeschungen nicht >3x Hinzufuegungen | Optional |

## Dashboard

Web-Dashboard auf Port 7777 mit:

- **Status-Karten:** Modus, SCM-Verbindung
- **Metriken-Tabelle:** Commands/Events mit Count, Errors, Avg Latency
- **REST-API:** `/api/v1/dashboard/status`, `/api/v1/dashboard/metrics`, `/api/v1/health`
- **Webhook-Endpunkt:** `POST /api/v1/webhook` (Gitea/GitHub Signatur-Validierung)
- Auto-Refresh alle 10 Sekunden

## Konfiguration

| Datei | Beschreibung |
|-------|-------------|
| `config/agent.json` | Log-Level, Datenverzeichnis, Modus, Parallelitaet, Sequence-Validator (warn/block/off) |
| `config/audit.json` | Audit-Sink (JSONL mit Rotation) |
| `config/eval.json` | Bewertungsgewichte und Baseline-Schwellwerte |
| `config/gates.json` | Required/Optional/Disabled Gates |
| `config/hooks.json` | Quality-Check-Konfiguration pro Extension |
| `config/notifications.json` | Slack, Teams, Webhook-Adapter |
| `config/privacy.json` | PII-Scrubbing, Drittland-Transfer, Retention |
| `config/repo_patterns.json` | Erwartete Event-Sequenzen pro Repo-Typ |
| `config/llm/defaults.json` | LLM-Defaults (max_tokens, temperature, circuit_breaker) |
| `config/workflows/*.json` | Workflow-Definitionen |

## Tests

```bash
# Alle Tests
python -m pytest

# Nur einen Slice testen
python -m pytest samuel/slices/planning/tests/

# E2E-Integration
python -m pytest tests/test_integration_e2e.py

# Architektur-Validierung (keine Cross-Slice-Imports)
python -m pytest tests/test_architecture_v2.py
```

**Aktueller Stand:** 644 Tests, Lint: ruff 0 errors.

## LLM-Provider

Unterstuetzte Provider (konfigurierbar via `.env`):

| Provider | Env-Variable | Beschreibung |
|----------|-------------|-------------|
| Ollama | `OLLAMA_URL` | Lokal, kostenlos, Standard |
| DeepSeek | `DEEPSEEK_API_KEY` | Cloud-API |
| Claude | `ANTHROPIC_API_KEY` | Anthropic Cloud |
| LM Studio | `LMSTUDIO_URL` | Lokal, OpenAI-kompatibel |

Alle Provider werden mit **Circuit-Breaker** und **Sanitizer** gewrappt.

## Sicherheit

- **Prompt Guard:** Unveraenderliche Schranken in jedem LLM-Prompt
- **Secret-Scanner:** Regex-basierte Erkennung von API-Keys, Tokens, Passwoertern
- **Prompt-Injection-Erkennung:** 7 Muster (ignore instructions, system prompt, ...)
- **Command-Safety:** Blockiert DROP, DELETE FROM, TRUNCATE, rm -rf, force-push
- **HMAC-Signierung:** Webhook-Payloads und Context-Slices
- **Audit-Trail:** JSONL mit Correlation-IDs, querybar nach Issue/Event/OWASP-Risk

## Lizenz

Proprietaer. Alle Rechte vorbehalten.
