# S.A.M.U.E.L. v2 — Technische Dokumentation

## Architektur

Event-Driven Monolith mit Vertical Slices, Ports & Adapters.

### Verzeichnisstruktur

```
samuel/
├── core/           # Shared Kernel (Bus, Events, Commands, Config, Ports)
├── adapters/       # Externe Integrationen
│   ├── api/        # REST-API + Webhook-Ingress + Auth
│   ├── audit/      # JSONL-Audit-Sink + Async-Buffer
│   ├── auth/       # StaticTokenAuth
│   ├── gitea/      # GiteaAdapter (IVersionControl)
│   ├── github/     # GitHubAdapter + GitHubAppAuth
│   ├── llm/        # 4 LLM-Adapter + CircuitBreaker + Sanitizer
│   ├── notifications/ # Slack, Teams, Generic Webhook
│   ├── quality/    # IQualityCheck-Registry + Checks
│   ├── secrets/    # EnvSecretsProvider
│   └── skeleton/   # 5 Skeleton-Builder (Python, TS, Go, SQL, Config)
├── slices/         # 21 Domain-Slices
│   ├── ac_verification/  # Akzeptanzkriterien-Checks
│   ├── architecture/     # Architektur-Validierung
│   ├── audit_trail/      # Audit-Bridge + OWASP-Mapping
│   ├── changelog/        # Changelog-Generierung
│   ├── code_analysis/    # Code-Analyse
│   ├── context/          # Kontext-Builder + Skeleton
│   ├── dashboard/        # Dashboard-Handler
│   ├── evaluation/       # Scoring + History
│   ├── healing/          # Self-Healing via LLM
│   ├── health/           # Health-Checks
│   ├── implementation/   # LLM-Loop + Patch-Parser
│   ├── planning/         # Plan-Generierung + Validierung
│   ├── pr_gates/         # 14 PR-Gates
│   ├── privacy/          # PII-Scrubber + DSGVO + AI-Act
│   ├── quality/          # Quality-Pipeline
│   ├── review/           # Code-Review via LLM
│   ├── security/         # Prompt-Injection-Erkennung
│   ├── sequence/         # Workflow-Sequenz-Validierung
│   ├── session/          # Session-Management
│   ├── setup/            # Setup-Wizard + Verzeichnisse
│   └── watch/            # Issue-Polling + Label-Management
├── premium/        # Optional: LLM-Routing + Token-Limit
├── cli.py          # CLI Entry-Point
├── server.py       # HTTP-Server + Dashboard
└── __main__.py     # python -m samuel
```

### Datenfluss

```
Issue (Gitea) → WatchHandler → IssueReady Event
  → WorkflowEngine → PlanIssueCommand
  → PlanningHandler → LLM → PlanCreated
  → ImplementCommand → LLM-Loop → Patches → CodeGenerated
  → CreatePRCommand → 14 Gates → PRCreated
  → EvaluateCommand → Scoring → EvalCompleted
```

### Bus-Middleware-Kette

1. IdempotencyMiddleware (Deduplizierung)
2. SecurityMiddleware (Command-Blocking)
3. PromptGuardMiddleware (Prompt-Injection-Schutz)
4. AuditMiddleware (Audit-Trail + Secret-Scrubbing)
5. ErrorMiddleware (Error-Recovery + WorkflowAborted)
6. MetricsMiddleware (Latenz + Zähler)

## API-Endpoints

| Methode | Pfad | Beschreibung | Auth |
|---------|------|-------------|------|
| GET | `/` | Dashboard HTML | Nein |
| GET | `/api/v1/health` | Health-Check | Ja |
| GET | `/api/v1/dashboard/status` | Status + Metriken | Nein |
| GET | `/api/metrics` | Prometheus-kompatible Metriken | Ja |
| POST | `/api/v1/issues/{id}/plan` | Plan-Generierung auslösen | Ja |
| POST | `/api/v1/issues/{id}/implement` | Implementation auslösen | Ja |
| POST | `/api/v1/scan` | Issue-Scan auslösen | Ja |
| POST | `/api/v1/webhook` | Gitea/GitHub Webhook-Empfang | Signatur |

Auth: `Authorization: Bearer <SAMUEL_API_KEY>` oder `X-API-Key: <key>`

## Konfiguration

| Datei | Beschreibung |
|-------|-------------|
| `.env` | SCM-Token, LLM-Keys, SAMUEL_API_KEY |
| `config/agent.json` | Agent-Einstellungen, Polling, Context-Limits |
| `config/llm/defaults.json` | LLM-Defaults (max_tokens, temperature, circuit_breaker) |
| `config/gates.json` | PR-Gate Konfiguration (required/optional/disabled) |
| `config/eval.json` | Evaluations-Kriterien + Gewichte |
| `config/privacy.json` | PII-Scrubbing, Drittland-Transfer, Retention |
| `config/notifications.json` | Slack/Teams/Webhook-Konfiguration |
| `config/hooks.json` | Quality-Check-Konfiguration pro Extension |
| `config/workflows/*.json` | 7 Workflow-Varianten |

## Deployment

### Systemd
```bash
cp samuel.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now samuel
```

### Docker
```bash
docker compose up -d
```

### Reverse-Proxy (nginx)
```nginx
location /samuel/ {
    proxy_pass http://127.0.0.1:7777/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## Entwicklung

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ samuel/ -v
ruff check .
```
