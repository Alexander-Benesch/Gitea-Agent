# S.A.M.U.E.L. v2 — Phasen-Workflow (Anweisung für neue Sessions)

Du implementierst **eine Phase komplett**, bevor die nächste beginnt. Für jede Phase gilt ein **striktes 3-Stufen-Protokoll**: Implementation → Phase-Review → QS-Check. Kein Schritt wird übersprungen. Kein "fertig" ohne belegbare Evidenz.

## 1. Kontext (einmalig einlesen)

**Repo:** `/home/ki02/samuel/` (Gitea: `Alexmistrator/S.A.M.U.E.L` auf `http://192.168.1.60:3001`, Token in `/home/ki02/gitea-agent/.env`)

**Pflicht-Lektüre vor Phase-Start:**
1. `.claude/CLAUDE.md` — Arbeitsregeln & Architektur-Leitplanken
2. `docs/V2.1_GAP_ANALYSE_THEMATISCH.md` — Detail-Beschreibung jedes Findings
3. `docs/SAMUEL_ARCHITECTURE_V2.1.md` — Zielarchitektur (18 Kapitel)
4. `docs/SAMUEL_V2_UMSETZUNGSPLAN.md` — Phasenplan

**Ausgangszustand (Stand 2026-04-16):**
- Phasen 0a-8 ✅ fertig, gemerged
- Phasen 9 + 10 offen (Issues #52, #53, #60-#70) — **müssen VOR Phase 11 abgeschlossen sein**
- Phasen 11-13 (neu): Issues #91-#121

**Reihenfolge verbindlich:**
```
Phase 9 → Phase 10 → Phase 11 → Phase 12 → Phase 13
```
Keine Mischung. Keine "ich mach nebenbei schnell X in Phase 13".

## 2. Pro Phase: 3-Stufen-Protokoll

### Stufe 1 — Implementation

**Pro Task-Issue einzeln:**

1. **Issue lesen** — Body komplett, alle Finding-IDs notieren
2. **Für jeden Finding-ID:** Source-Referenz in `V2.1_GAP_ANALYSE_THEMATISCH.md` aufschlagen, v1-Code an Originalstelle lesen (`Read`-Tool, nicht `--get-slice`)
3. **Branch:** `phase/<nr>-<kurzname>` von `main`
4. **Vor jedem Edit:** `Grep` ob Variable/Funktion schon existiert — Dopplungen sind verboten
5. **Implementieren:** ein Finding = ein Commit, Commit-Message-Format:
   ```
   feat(samuel): <kurz> (Finding <ID>, Issue #<nr>)

   - Quelle V2.1: <Sektion>
   - v1-Ursprung: <datei>:<zeile>
   - Tests: <test-pfad>
   ```
6. **Test pro Finding:** jede Änderung braucht mindestens einen Test (pytest) oder eine Config-Validierung
7. **Checkbox im Issue abhaken** erst wenn Commit gepusht UND Test grün

**Scope-Disziplin:** Fällt ein weiterer Bug auf, der nicht im aktuellen Issue steht → NEUES Gitea-Issue anlegen, nicht mitfixen.

### Stufe 2 — Phase-Review (nach allen Tasks der Phase)

**Erst hier wird das Phase-Overview-Issue abgehakt.** Review ist eine **eigene Session**, idealerweise frische Chat-Instanz um Bias zu vermeiden.

**Pro Task-Issue der Phase durchgehen:**

| Check | Kommando/Tool | Beweis |
|---|---|---|
| Jeder Finding-ID hat abgehakte Checkbox | Issue-Body lesen | Screenshot/Liste |
| Jeder Finding-ID ist im Code umgesetzt | `Grep` nach Ziel-Pfad aus Gap-Tabelle | Dateipfad + Zeile |
| Alter v1-Code ist bereinigt (falls anwendbar) | `Grep` nach altem Symbol in `/home/ki02/samuel/` | Keine Treffer in v2 |
| Config-Werte sind extrahiert (nicht mehr hardcoded) | `Grep` nach dem Hardcoded-Wert | Nur noch in Test-Fixtures |
| Test existiert und läuft | `pytest <slice>/tests/ -k <finding>` | grüner Output |
| Architektur-Regel nicht verletzt | `pytest tests/test_architecture_v2.py` | grün |

**Review-Ergebnis in den Phase-Overview-Kommentar posten** als Tabelle mit allen Findings + Evidenz-Spalte. Erst wenn JEDE Zeile grün ist, Overview-Issue schließen.

### Stufe 3 — QS-Check (Gesamt, frische Sicht)

**Nach Stufe 2 in separater Chat-Session** die Phase ganzheitlich prüfen:

**Kommandos (alle müssen grün sein):**
```bash
cd /home/ki02/samuel
pytest samuel/ tests/ -v                    # Unit + Integration
pytest tests/test_architecture_v2.py -v     # Slice-Isolation
ruff check samuel/ tests/                   # Lint (wenn Phase 12.4 durch)
mypy --strict samuel/                       # Types (wenn Phase 12.4 durch)
python3 -m samuel.cli --doctor --json       # System-Selbstcheck
```

**End-to-End-Smoke-Test der geänderten Slices:**
- Den Workflow, den die Phase betrifft, einmal manuell über die CLI/API durchspielen
- Bei Dashboard-Änderungen: Browser öffnen, Seite klicken, Feature tatsächlich benutzen
- Audit-Log prüfen: sind die neuen Events drin?

**Regressions-Check:**
```bash
# Letzten grünen Baseline-Commit vor der Phase finden
git log --oneline main..HEAD
# Existierende Tests laufen weiter grün?
pytest samuel/ tests/ --lf  # last-failed
```

**Doku-Check:**
- `docs/SAMUEL_ARCHITECTURE_V2.1.md` aktualisiert, falls Architektur berührt?
- `docs/SAMUEL_V2_UMSETZUNGSPLAN.md` Phase als abgeschlossen markiert?
- Phase-spezifische Dokumente vorhanden? (z.B. Phase 11: `docs/DSGVO_VVT.md`, `docs/AI_ACT_TECHNICAL_DOC.md`)

**QS-Ergebnis als Kommentar am Phase-Overview-Issue:**
```markdown
## QS-Check Phase <nr> — <datum>

- [ ] pytest alle grün (<zahl> Tests)
- [ ] Architecture-Tests grün
- [ ] Lint + Typen grün
- [ ] End-to-End-Smoke erfolgreich (<welcher Workflow>)
- [ ] Keine Regression (<git diff-Stat>)
- [ ] Doku aktualisiert (<welche Dateien>)

**Befund:** <entweder "ready to close" oder konkrete Restarbeiten als neue Issues>
```

## 3. Anti-Vergessen-Regeln (explizit)

1. **"Fertig" gibt es nur mit Beleg.** Kein "habe implementiert" ohne Zeilennummer + Testname.
2. **Checkbox abhaken = Commit gepusht + Test grün.** Nicht "ich mache das gleich".
3. **Overview-Issue schließen = alle Task-Issues geschlossen + QS-Check-Kommentar gepostet.**
4. **`Read`-Tool vor `Edit`-Tool.** `--get-slice` zählt nicht als "gelesen".
5. **`Grep` vor neuer Deklaration.** Existiert die Variable/Funktion schon irgendwo?
6. **End-to-End verifizieren.** Backend-Änderung → auch Parser, Templates, JS, Deployment prüfen.
7. **Bei manuellen ACs stoppen.** Nach Verify-Request: STOPPEN, dem User berichten, User entscheidet.
8. **Keine Self-Approval.** Wer implementiert, approved nicht den Phase-Review derselben Phase.
9. **Scope-Creep = neues Issue.** Bugs die beim Arbeiten auffallen: auf Gitea als Issue anlegen, nicht mitfixen.
10. **Phase-Grenzen respektieren.** Ein Phase-12-Finding während Phase-11-Arbeit = neues Issue, nicht vorziehen.

## 4. Rollen pro Phase (empfohlen: verschiedene Chat-Sessions)

| Session | Rolle | Tool-Fokus |
|---|---|---|
| A | Implementation | Read, Edit, Write, Bash (commit/push) |
| B | Phase-Review | Read, Grep, Bash (pytest, git log) — KEIN Edit |
| C | QS-Check | Read, Grep, Bash (tests, smoke) — KEIN Edit |

**Grund:** Gleiche Session hat Bestätigungs-Bias. Fresh Chat sieht nur den Endzustand und muss sich die Evidenz selbst erarbeiten.

## 5. Phasen-Reihenfolge & Besonderheiten

### Phase 9 (offen) — Aufräumen
- Vor Phase 11 zwingend. Entscheidet, welche v1-Funktionen in v2 migriert werden.
- **Achtung:** Viele Phase-13-Findings (Sektion 15 "Vergessene v1-Funktionen") hängen vom Ergebnis ab. Phase 9 kann Phase-13-Issues obsolet machen.

### Phase 10 (offen) — Server-Hook + Flexibilität
- Enthält bereits `E11` (--no-verify Bypass) und `T14` (GitHub-Support).
- Vor Phase-13-Security-Issues abschließen.

### Phase 11 — Compliance
- Regulatorischer Track, kann parallel zu Phase 12 laufen
- **Pflicht-Outputs:** `docs/DSGVO_VVT.md`, `docs/AI_ACT_TECHNICAL_DOC.md`, `docs/AI_ACT_COMPLIANCE.md`

### Phase 12 — Hardening
- `pyproject.toml` existiert bereits → V1 teilweise abgehakt, aber Completeness prüfen
- `12.4` (Best Practice) führt ruff/mypy ein → ab hier sind Lint-Checks in QS-Check Pflicht

### Phase 13 — Vergessenes & Konzeptfehler
- **Top-Prioritäten zuerst:**
  1. `#103` (Injection-Lücken, E7 Top-1) — KRITISCH
  2. `#108` (Architektur-Inkonsistenzen, M3 Top-4) — KRITISCH, Semaphore-Leak
  3. `#107` (Fehlende Events, O6 Top-13)
  4. `#111` + `#112` (Error-Handling, L1 Top-6 + L2 Top-14)

## 6. Ende einer Phase

Eine Phase ist erst dann abgeschlossen, wenn ALLE folgenden Bedingungen gelten:

- [ ] Alle Task-Issues der Phase geschlossen
- [ ] Phase-Overview-Issue geschlossen mit QS-Check-Kommentar
- [ ] PR in `main` gemerged
- [ ] Tag gesetzt: `phase-<nr>-complete`
- [ ] `docs/SAMUEL_V2_UMSETZUNGSPLAN.md` Phase als ✅ markiert
- [ ] Memory aktualisiert: `project_samuel_v2.md` mit "Phase X abgeschlossen am YYYY-MM-DD"

**Erst dann** darf die nächste Phase gestartet werden.

---

## Start-Prompt für neuen Chat

> Lies `.claude/CLAUDE.md` und `docs/PHASE_WORKFLOW.md`. Aktuelle Aufgabe: **Phase \<N\>**. Beginne mit Stufe 1 (Implementation), pro Task-Issue separat. Nach jedem Task-Issue: kurze Statusmeldung, dann weiter. Kein Überspringen von Stufen.
