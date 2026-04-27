# Changelog

All notable changes to S.A.M.U.E.L. v2.

## [2.0.0-alpha] - 2026-04-17

### Phase 0a: Vorarbeiten
- Pre-commit hooks und Test-Konventionen

### Phase 0b: Shared Kernel
- Event-Bus, Commands, Config, Ports, Types

### Phase 1: Audit-Trail
- JSONL-Audit-Sink mit Rotation und Correlation-IDs

### Phase 2: SCM-Port
- IVersionControl, GiteaAdapter, IAuthProvider

### Phase 3: LLM-Port
- ILLMProvider, CircuitBreaker, SanitizingAdapter

### Phase 4: Planning-Slice
- PlanIssueCommand, 3-Stufen LLM-Qualitaetskontrolle

### Phase 5: Implementation-Slice
- IPatchApplier-Registry, Resume mit WorkflowCheckpoint

### Phase 6: PR-Gates-Slice
- 14 PR-Gates, config/gates.json

### Phase 7: Evaluation-Slice
- Eval-Score-History, Baseline-Threshold

### Phase 8: Watch, Healing, Dashboard + restliche Slices
- 23 Slices komplett, Semaphore-kontrollierte Parallelitaet

### Phase 9: Aufräumen
- v1-Dateien entfernt (commands/, plugins/)
- v1→v2 Mapping-Test
- Sequence-Validator

### Phase 10: Server-Hook + Flexibilität
- Gitea pre-receive Hook
- GitHubAdapter + GitHubAppAuth
- IQualityCheck Registry (Python, TypeScript)
- Skeleton-Builder (Python, TypeScript, Go, SQL, Config)

### Phase 11: Compliance
- PromptSanitizer (PII-Scrubbing)
- TransferWarning (Drittland-Transfer DSGVO)
- AI-Attribution-Trailer (EU AI Act Art. 50)
- DSGVO VVT, AI Act Technical Documentation

### Phase 12: Hardening
- Dockerfile + docker-compose.yml
- pyproject.toml mit allen Extras
- TLS-Verify konfigurierbar
- MetricsMiddleware

### Phase 13: Vergessenes & Konzeptfehler
- E7 Code-Injection Fix (AC-Tag Sanitization)
- M3 Semaphore-Leak Fix
- OpenRouter Pricing Integration
- 6 neue Events, 4 Config-Bereiche externalisiert
