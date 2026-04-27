# Verzeichnis der Verarbeitungstaetigkeiten (VVT)

> Gemaess Art. 30 DSGVO (VO 2016/679)

**Verantwortlicher:** Betreiber der S.A.M.U.E.L.-Instanz
**Stand:** 2026-04-17

---

## 1. Verarbeitungstaetigkeit: Issue-Analyse und Planungserstellung

| Feld | Inhalt |
|------|--------|
| Zweck | Analyse von Gitea/GitHub-Issues zur automatisierten Planerstellung |
| Rechtsgrundlage | Art. 6 (1f) — berechtigtes Interesse an Softwareentwicklungs-Automatisierung |
| Kategorien betroffener Personen | Issue-Ersteller, zugewiesene Entwickler |
| Kategorien personenbezogener Daten | Benutzername, Issue-Texte (koennen PII enthalten) |
| Empfaenger | LLM-Provider (gemaess `config/privacy.json → provider_locations`) |
| Drittland-Transfer | Abhaengig vom Provider — siehe Abschnitt 6 |
| Loeschfristen | Audit-Log: 365 Tage. PII-Anonymisierung: 30 Tage |
| TOMs | PII-Scrubbing vor LLM-Calls, TLS-Transport, Token-Auth |

## 2. Verarbeitungstaetigkeit: Code-Generierung via LLM

| Feld | Inhalt |
|------|--------|
| Zweck | Automatisierte Code-Generierung basierend auf Planvorgaben |
| Rechtsgrundlage | Art. 6 (1f) — berechtigtes Interesse |
| Kategorien personenbezogener Daten | Code-Kontext (kann Entwicklernamen, Kommentare enthalten) |
| Empfaenger | LLM-Provider |
| Drittland-Transfer | Abhaengig vom Provider |
| Loeschfristen | Kein persistenter Speicher beim LLM-Provider (API-Calls) |
| TOMs | PromptSanitizer, PromptGuardMiddleware, Context-Minimierung |

## 3. Verarbeitungstaetigkeit: Audit-Trail

| Feld | Inhalt |
|------|--------|
| Zweck | Nachvollziehbarkeit aller Agenten-Aktionen (Compliance, Debugging) |
| Rechtsgrundlage | Art. 6 (1c) — rechtliche Verpflichtung (EU AI Act Art. 12) |
| Kategorien personenbezogener Daten | Benutzernamen, Correlation-IDs, Event-Metadaten |
| Empfaenger | Nur lokal (JSONL-Datei) |
| Drittland-Transfer | Keiner (lokale Speicherung) |
| Loeschfristen | 365 Tage. PII nach 30 Tagen anonymisiert |
| TOMs | Dateisystem-Berechtigungen, HMAC-Integritaet |

## 4. Verarbeitungstaetigkeit: Dashboard und Metriken

| Feld | Inhalt |
|------|--------|
| Zweck | Monitoring und Statusuebersicht fuer Betreiber |
| Rechtsgrundlage | Art. 6 (1f) — berechtigtes Interesse |
| Kategorien personenbezogener Daten | Aggregierte Metriken (keine direkten PII) |
| Empfaenger | Dashboard-Nutzer (lokales Netzwerk) |
| Drittland-Transfer | Keiner |
| TOMs | CSRF-Schutz, Netzwerk-Segmentierung |

## 5. Technische und organisatorische Massnahmen (TOMs)

| Massnahme | Beschreibung | Konfiguration |
|-----------|-------------|---------------|
| PII-Scrubbing | E-Mail, IP, Telefon, Kreditkarten werden vor LLM-Calls entfernt | `config/privacy.json → pii_scrubbing` |
| Retention-Policy | Audit-Logs nach 365 Tagen geloescht, PII nach 30 Tagen anonymisiert | `config/privacy.json → retention` |
| Drittland-Warnung | Dashboard zeigt Warnung bei Providern ausserhalb EU/EEA | `config/privacy.json → transfer_warning` |
| Transport-Verschluesselung | HTTPS/TLS fuer alle API-Calls | Standard |
| Token-Authentifizierung | SCM- und LLM-Token als Umgebungsvariablen, nie im Code | `.env` |
| Prompt-Guard | Unveraenderliche Schranken in jedem LLM-Prompt | Bus-Middleware |
| Audit-Trail | Jede Aktion mit Correlation-ID protokolliert | JSONL + OWASP-Klassifikation |

## 6. Drittland-Transfer nach Provider

| Provider | Standort | Transfer | Schutzmassnahme |
|----------|----------|----------|-----------------|
| Ollama | Lokal | Keiner | — |
| LM Studio | Lokal | Keiner | — |
| DeepSeek | CN | Ja | SCCs erforderlich, Warnung im Dashboard |
| Anthropic (Claude) | US | Ja | EU-US Data Privacy Framework, DPA erforderlich |
| OpenAI | US | Ja | EU-US Data Privacy Framework, DPA erforderlich |

## 7. DPA-Anforderungen pro Provider

Fuer jeden Cloud-Provider muss ein Data Processing Agreement (Art. 28 DSGVO) vorliegen:

- **Anthropic:** https://www.anthropic.com/policies/privacy — DPA auf Anfrage
- **OpenAI:** https://openai.com/policies/data-processing-agreement
- **DeepSeek:** Kein Standard-DPA verfuegbar — SCCs + TIA (Transfer Impact Assessment) erforderlich

**Hinweis:** Lokale Provider (Ollama, LM Studio) benoetigen kein DPA, da keine Daten das lokale System verlassen.
