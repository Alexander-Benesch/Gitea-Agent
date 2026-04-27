# S.A.M.U.E.L. — EU AI Act Compliance

> Bezug: EU AI Act (VO 2024/1689), in Kraft seit 01.08.2024

## 1. Risikoklassifikation (Art. 6)

**Einstufung: Limited Risk**

S.A.M.U.E.L. ist ein KI-gestuetztes Software-Entwicklungswerkzeug. Es faellt
NICHT unter die High-Risk-Kategorie (Annex III), da es:

- Keine biometrischen Daten verarbeitet
- Keine kritische Infrastruktur steuert
- Keine Beschaeftigungs- oder Kreditentscheidungen trifft
- Nicht in Strafverfolgung oder Migration eingesetzt wird

**Anwendbare Pflichten:** Transparenzpflichten nach Art. 50.

## 2. Menschliche Aufsicht / Human Oversight (Art. 14) — F1

**Status: Bereits erfuellt (USP des Systems)**

S.A.M.U.E.L. ist von Grund auf als "Human-in-the-Loop"-System konzipiert:

| Mechanismus | Beschreibung |
|------------|-------------|
| 14 PR-Gates | Kein Pull Request ohne 14 automatisierte Pruefungen |
| Plan-Review | LLM-generierte Plaene koennen abgelehnt werden |
| Gate-Konfiguration | Einzelne Gates per `config/gates.json` als required/optional/disabled |
| Semaphore-Concurrency | Begrenzte Parallelitaet verhindert unkontrollierten Durchsatz |
| Watch-Mode | Manuell startbar, explizite Konfiguration |
| Self-Mode-Parity | Wenn der Agent auf sich selbst arbeitet, gelten zusaetzliche Tests |

## 3. KI-generierter Code kennzeichnen (Art. 50 Abs. 1) — F2

**Pflicht:** Jeder KI-generierte Commit muss maschinenlesbar gekennzeichnet sein.

**Umsetzung:** Git-Trailer in jeder Commit-Message:

```
AI-Generated-By: <model>@<version>
```

Beispiel:
```
feat: Add retry logic for API calls

AI-Generated-By: ollama/codellama@latest
```

**Implementierung:** `samuel.slices.privacy.ai_act.ai_attribution_trailer()`

## 4. Recht auf Erklaerung (Art. 86, DSGVO Art. 22) — F4

**Pflicht:** Jede KI-Entscheidung muss nachvollziehbar sein.

**Umsetzung:** `LLMCallCompleted`-Events enthalten:

| Feld | Beschreibung |
|------|-------------|
| `prompt_hash` | SHA-256 Hash des Prompts (ohne PII) |
| `system_prompt_version` | Version der System-Anweisungen |
| `temperature` | LLM-Temperature-Parameter |
| `model_version` | Exaktes Modell + Version |
| `correlation_id` | Verknuepfung mit dem ausloesenden Issue |

**Implementierung:** `samuel.slices.privacy.ai_act.enrich_llm_event_payload()`

## 5. Genauigkeit und Robustheit (Art. 15) — O3

**Nachweis durch:**

- **Eval-Score-History:** Jede Code-Generierung wird bewertet (Score 0-100%)
- **Baseline-Threshold:** Konfigurierbar in `config/eval.json`
- **Fail-Fast:** Bei kritischen Fehlern sofortige Blockierung unabhaengig vom Gesamtscore
- **Healing:** Automatische Fehlerkorrektur mit Budget-Kontrolle

## 6. Automatische Protokollierung (Art. 12) — O4

**Pflicht:** Rueckverfolgbarkeit aller Entscheidungen.

**Umsetzung:**

- JSONL Audit-Trail mit `correlation_id` in jedem Event
- Retention: 365 Tage (Art. 12 Abs. 2 fordert "angemessene Dauer")
- PII-Anonymisierung nach 30 Tagen (DSGVO Art. 5 Abs. 1e)
- OWASP-Klassifikation fuer Security-Events
- Query-API: `AuditQuery` mit Filter nach Issue, Event, OWASP-Risk
