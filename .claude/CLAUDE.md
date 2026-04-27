# CLAUDE.md — S.A.M.U.E.L. v2

## Projekt-Kontext

- **Arbeitsverzeichnis:** `/home/ki02/samuel/` — das neue v2-Repo
- **NICHT anfassen:** `/home/ki02/gitea-agent/` — v1, ARCHIVIERT (read-only auf Gitea). Nur als Referenz zum Lesen, keine Änderungen, keine Commits
- **Gitea-Repo:** `Alexmistrator/S.A.M.U.E.L` auf `http://192.168.1.60:3001`
- **Gitea-Token:** in `/home/ki02/gitea-agent/.env` (GITEA_TOKEN)

## Dokumente (Priorität der Lektüre)

1. **`docs/PHASE_WORKFLOW.md`** — Verbindliches 3-Stufen-Protokoll (Implementation → Phase-Review → QS-Check) für alle Phasen ab 11. IMMER ZUERST LESEN bei Phasen 11-13.
2. **`docs/phases/PHASE_Xn.md`** — Detaillierte Aufgabenbeschreibung der aktuellen Phase (falls vorhanden). Enthält exakte Spezifikationen, Fallstricke, und was NICHT anwendbar ist. Der User sagt welche Phase dran ist.
3. `docs/V2.1_GAP_ANALYSE_THEMATISCH.md` — Detail-Beschreibung aller 248 Findings aus der Gap-Analyse. Quelle für Phase 11-13.
4. `docs/SAMUEL_ARCHITECTURE_V2.1.md` — Zielarchitektur (2856 Zeilen, 18 Kapitel). Bei Detail-Fragen konsultieren.
5. `docs/SAMUEL_V2_UMSETZUNGSPLAN.md` — Gesamtübersicht aller Phasen (808 Zeilen). Für Kontext und Abhängigkeiten.

Die Phase-Datei bzw. der Phasen-Workflow ist die operative Anweisung. Die Architektur-Docs sind Referenz. Nicht raten — nachlesen.

## Arbeitsablauf pro Chat-Session

### 1. Phase-Datei lesen

Der User sagt welche Phase dran ist (z.B. "Phase 0b").
**`docs/phases/PHASE_0b.md` lesen** — dort steht alles: Aufgaben, Reihenfolge, Akzeptanzkriterien, was NICHT gilt.

### 2. Issue auf Gitea erstellen

Zu Beginn jeder Phase ein Issue erstellen:
- Titel: `Phase 0b: Shared Kernel bauen`
- Body: Aufgaben als Checkboxen aus dem Umsetzungsplan
- Label: (keine speziellen nötig)

### 3. Branch erstellen

Pro Phase ein Branch von `main`:
```
git checkout main && git pull
git checkout -b phase/0b-shared-kernel
```

### 4. Implementieren

- Code schreiben gemäß Architektur-Dokument
- Tests schreiben (jede Datei bekommt Tests)
- Committen mit Referenz auf Issue: `feat: Bus + Middleware (#ISSUE_NR)`

### 5. Phase abschließen

- Alle Akzeptanzkriterien aus dem Umsetzungsplan prüfen
- Tests laufen: `python3 -m pytest tests/ samuel/ -v`
- PR erstellen → in main mergen
- Issue schließen, Checkboxen abhaken

## v1-Code als Referenz

Beim Portieren von Logik aus v1:
- v1 liegt in `/home/ki02/gitea-agent/`
- Logik verstehen, dann NEU schreiben für v2-Architektur
- NICHT kopieren und anpassen — die Architektur ist fundamental anders
- Imports: `from samuel.core.X import Y` — nie `from plugins` oder `from commands`

## Regeln

- Kein Code im Root — aller Python-Code unter `samuel/`
- Kein Slice importiert einen anderen Slice
- Slices importieren nur den Shared Kernel (`samuel.core.*`)
- Externe Systeme nur über Ports (`samuel.core.ports`)
- Tests leben beim Slice: `samuel/slices/planning/tests/test_handler.py`
- Übergreifende Tests (Architecture): `tests/test_architecture_v2.py`
