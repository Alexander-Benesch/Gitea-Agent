# Pipeline: Issue → LLM-Prompt

Technische Beschreibung jedes Knotenpunkts in der Context-Building-Pipeline.
Ziel: Nachvollziehbarkeit des Ablaufs — wo kommt was her, wo geht es hin,
welche Dateien sind beteiligt, welche Sprachen werden unterstützt,
welche Voraussetzungen gelten.

**Stand:** Phase 14.11 (commit ab 2026-04-17).

---

## Inhalt

1. [Übersichts-Flussdiagramm](#übersichts-flussdiagramm)
2. [K1 — Issue-Input (Event + SCM)](#k1--issue-input)
3. [K2 — `iter_project_files()` Datei-Iteration](#k2--iter_project_files)
4. [K3 — `extract_keywords()` Keyword-Extraktion](#k3--extract_keywords)
5. [K4 — `extract_plan_files()` Plan-File-Erkennung](#k4--extract_plan_files)
6. [K5 — Architecture-Context (Rollen + Scopes)](#k5--architecture-context)
7. [K6 — `expand_via_symbol_references()` Transitive Dateien](#k6--expand_via_symbol_references)
8. [K7 — Skeleton-Builders (pro Sprache)](#k7--skeleton-builders)
9. [K8 — `filter_skeleton()` Symbol-Matching gegen Issue](#k8--filter_skeleton)
10. [K9 — `grep_keywords()` Keyword-Suche im Projekt](#k9--grep_keywords)
11. [K10 — `render_files_section()` Smart-File-Load](#k10--render_files_section)
12. [K11 — `build_full_context()` Kontext-Aggregation](#k11--build_full_context)
13. [K12 — `_build_implement_prompt()` Prompt-Assembly](#k12--_build_implement_prompt)
14. [K13 — `validate_context()` Pre-LLM Validator](#k13--validate_context)
15. [K14 — `run_llm_loop()` LLM-Call mit Retry](#k14--run_llm_loop)
16. [K15 — `patch_parser` + Applier](#k15--patch_parser)
17. [K16 — Git-Operationen + `CodeGenerated`-Event](#k16--git-operationen)
18. [Anhang: Config-Dateien die die Pipeline steuern](#anhang-config-dateien)

---

## Übersichts-Flussdiagramm

```
                         ┌─────────────────────────┐
                         │ K1  Issue (Gitea-API)   │
                         │ title, body, plan_comm. │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
           ┌────────────────┐ ┌──────────────┐ ┌──────────────┐
           │ K3 Keywords    │ │ K4 Plan-Files│ │ K5 Arch-Ctx  │
           │ (Stop-Words)   │ │ (Backticks)  │ │ config/      │
           └───────┬────────┘ └──────┬───────┘ │ architecture │
                   │                 │         │ .json        │
                   │                 ▼         └──────┬───────┘
                   │      ┌──────────────────┐        │
                   │      │ K6 Symbol-Ref    │◄───────┤ allowed/blocked
                   │      │ Expansion        │        │ scopes
                   │      │ (sprachagnostic) │        │
                   │      └──────┬───────────┘        │
                   │             │                    │
                   │             ▼                    │
                   │      ┌──────────────────┐        │
                   │      │ K8 filter_skel.  │        │
                   │      │ (Issue × Skel)   │◄───────┤ module_info
                   │      └──────┬───────────┘        │
                   ▼             │                    │
           ┌────────────────┐    │                    │
           │ K9 grep_kw     │    │                    │
           │ (Word-Boundary)│◄───┴────────────────────┤
           └───────┬────────┘    │                    │
                   │             ▼                    │
                   │      ┌──────────────────┐        │
                   └─────►│ K10 render_files │        │
                          │ (smart-load)     │        │
                          └──────┬───────────┘        │
                                 ▼                    │
                          ┌──────────────────┐        │
                          │ K11 build_full_ │◄───────┘
                          │ context          │
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K12 Prompt-Build │
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K13 Validator    │──────► WorkflowBlocked
                          │ OK? ─ nein       │         (Abbruch)
                          └──────┬───────────┘
                           ja    │
                                 ▼
                          ┌──────────────────┐
                          │ K14 LLM-Loop     │──────► TokenLimitHit
                          │ (5 Runden max)   │         WorkflowBlocked
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K15 Patch apply  │
                          └──────┬───────────┘
                                 ▼
                          ┌──────────────────┐
                          │ K16 Git + Event  │
                          │ CodeGenerated    │──────► PR-Gates → PR
                          └──────────────────┘
```

---

## K1 — Issue-Input

**Datei:** `samuel/slices/implementation/handler.py`, Methode `ImplementationHandler.handle`

**Woher?** Drei Quellen:
- CLI: `python -m samuel run <issue_number>` → `cli.py:_cmd_run` publiziert `IssueReady` → WorkflowEngine sendet `ImplementCommand`
- REST-API: `POST /api/v1/issues/{id}/implement` → `adapters/api/rest.py:65`
- Workflow: Automatisch bei `PlanValidated`-Event

**Was passiert im Handler:**
```
cmd = ImplementCommand(issue_number=136, correlation_id=...)
↓
issue = self._scm.get_issue(136)      # Gitea API-Call
comments = self._scm.get_comments(136)
plan_text = comment mit "## Plan" oder "### Akzeptanzkriterien"
```

**Input für die Pipeline:**
- `issue_title: str`
- `issue_body: str`
- `plan_text: str` (kann leer sein)

**Beispiel-Issue:**
```
Title:  CLI: --version Flag hinzufügen
Body:   Die CLI soll einen `--version` Flag unterstützen.
        Version aus `samuel/__init__.py` lesen.
Plan:   ## Plan
        Änderungen in `samuel/cli.py`: argparse action='version'.
```

**Voraussetzungen:**
- SCM-Adapter verdrahtet (`GiteaAdapter` / `GitHubAdapter`)
- ENV: `SCM_URL`, `SCM_TOKEN`, `SCM_REPO`

**Geht an:** K3 (Keywords), K4 (Plan-Files), K11 (build_full_context)

---

## K2 — `iter_project_files()`

**Datei:** `samuel/core/project_files.py`

**Zweck:** Zentrale, sprachunabhängige Datei-Iteration. Ersetzt alle verstreuten `rglob()`-Aufrufe.

**Signatur:**
```python
iter_project_files(
    root: Path,
    *,
    extensions: Iterable[str] | None = None,
    max_size_kb: int | None = None,
    exclude_dirs: Iterable[str] | None = None,
    exclude_files: Iterable[str] | None = None,
    follow_symlinks: bool = False,
) -> Iterator[Path]
```

**Defaults (merged mit User-Angaben):**
- `DEFAULT_EXCLUDE_DIRS` (20 Einträge): `__pycache__, .git, .venv, venv, node_modules, .tox, .mypy_cache, .pytest_cache, dist, build, target, out, bin, obj, data, .cache, ...`
- `DEFAULT_EXCLUDE_FILES`: `package-lock.json, yarn.lock, poetry.lock, Cargo.lock, go.sum, Gemfile.lock, ...`

**Konstanten (importierbar):**
- `CODE_EXTENSIONS` (30+): `.py, .js, .ts, .tsx, .jsx, .go, .java, .kt, .scala, .rs, .rb, .php, .swift, .c, .cc, .cpp, .h, .hpp, .cs, .lua, .sh, .sql, ...`
- `CONFIG_EXTENSIONS`: `.json, .yaml, .yml, .toml, .ini, .env`
- `DOC_EXTENSIONS`: `.md, .rst, .txt, .adoc`

**Sprachen:** Alle — extension-basiert. Kein Parsing.

**Beispiel:**
```python
from samuel.core.project_files import iter_project_files, CODE_EXTENSIONS

for f in iter_project_files(Path("."), extensions=CODE_EXTENSIONS, max_size_kb=50):
    print(f.relative_to(Path(".").resolve()))
# samuel/core/bus.py
# samuel/cli.py
# ...
```

**Wer nutzt das?** K7 (Skeleton-Builder-Scan), K9 (grep_keywords). Nicht für Render direkt.

**Voraussetzungen:** Keine (stdlib only).

---

## K3 — `extract_keywords()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Extrahiert die wichtigsten Wörter aus Issue-Text. Diese dienen als Input für K9 (Grep) und helfen beim Skeleton-Matching indirekt.

**Algorithmus:**
1. Regex `[A-Za-z_][\w]{2,}` mit `re.UNICODE` — erkennt auch `hinzufügen`, `größe` (Umlaute)
2. Filterung gegen `_STOP_WORDS` (Set mit ~100 Einträgen, en + de)
3. Zählung nach Frequenz
4. Top 12 Keywords zurück

**Stop-Word-Kategorien:**
- Englisch: `issue, task, plan, code, file, the, and, for, ...`
- Deutsch: `soll, muss, wird, der, die, das, ist, mit, ohne, auf, beim, ...`
- Magic: `__init__, __main__, python, samuel` (Projekt-spezifisch)

**Input:** beliebige Text-Argumente (title, body, plan)

**Output:** `list[str]` — sortiert nach Häufigkeit

**Beispiel:**
```python
kw = extract_keywords(
    "CLI: --version Flag hinzufügen",
    "Die CLI soll einen `--version` Flag unterstützen.",
    "## Plan\nargparse action='version'",
)
# ['version', 'cli', 'flag', 'argparse', 'hinzufügen',
#  'action', 'unterstützen', ...]
```

**Sprachen:** Python-Regex mit UNICODE — alle lateinischen Schriften, auch Umlaute/Akzente.

**Geht an:** K9 (`grep_keywords` nutzt die Top-5).

---

## K4 — `extract_plan_files()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Findet explizit im Issue genannte Dateipfade (via Backtick-Regex).

**Regex:** `(?:^|[\s`'"])([a-zA-Z0-9_/.-]+(?:\.[a-zA-Z]{1,5}))(?=[\s`'\":,)]|$)`

Erfasst Patterns wie:
- `` `samuel/cli.py` ``
- `"samuel/server.py"`
- `config/agent.json`
- `tests/test_x.py`

**Filter:**
- `startswith("/", "http", "./")` → skip (keine absoluten/URL-Pfade)
- `".." in candidate` → skip (keine Parent-Referenzen)
- `len > 200` → skip
- **Datei muss existieren** im `project_root`

**Max Output:** `MAX_RELEVANT_FILES = 8`

**Beispiel:**
```python
body = "In `samuel/cli.py` den Parser anpassen, siehe `samuel/__init__.py`."
extract_plan_files(body, Path("."))
# ['samuel/cli.py', 'samuel/__init__.py']
```

**Sprachen:** Sprachagnostisch — funktioniert für alle Dateiformate mit Extension.

**Geht an:** K5 (Architecture), K6 (Expansion), K10 (render_files_section).

---

## K5 — Architecture-Context

**Dateien:**
- `config/architecture.json` — Konfiguration (user-editierbar)
- `samuel/slices/architecture/handler.py` — `ArchitectureHandler`
- `samuel/slices/implementation/context_builder.py` — Inline-Lader im `build_full_context` (kein Cross-Slice-Import)

**Zweck:** Beschränkt die Kontext-Expansion basierend auf der Rolle der Plan-Files. Verhindert dass ein Dashboard-UI-Issue plötzlich config/ durchsucht.

**Config-Schema (`config/architecture.json`):**
```json
{
  "global_constraints": [
    "Kein Slice importiert einen anderen Slice",
    "Externe Systeme nur über Ports"
  ],
  "modules": [
    {
      "path": "samuel/server.py",
      "role": "dashboard-frontend",
      "description": "HTTP-Server + Dashboard-HTML",
      "constraints": [
        "Keine Backend-Logik hier",
        "Keine Config-Änderungen bei UI-Issues"
      ]
    }
  ],
  "expansion_policy": {
    "dashboard-frontend": {
      "allowed_scopes": ["samuel/server.py", "samuel/slices/dashboard/"],
      "blocked_scopes": ["config/", "samuel/core/", "samuel/adapters/"]
    }
  }
}
```

**Resolution-Logik (`_resolve_expansion_scope`):**
1. Für jede Plan-File: matche gegen `modules[*].path` → sammle `roles`
2. Für jede gesammelte Rolle: merge `allowed_scopes` + `blocked_scopes` aus `expansion_policy`
3. Übergebe als Set an K6 + K9

**Path-Matching:**
- `"config/"` endet mit `/` → präfix-match
- `"samuel/server.py"` ohne `/` → exact oder präfix mit `/`

**Input:** Plan-Files (aus K4)

**Output:** `{"allowed": set[str], "blocked": set[str], "roles": set[str]}` + `module_info: list[dict]` für Prompt-Sektion

**Beispiel:**
```
Plan-File: samuel/server.py
→ Role: dashboard-frontend
→ allowed: {samuel/server.py, samuel/slices/dashboard/, tests/test_server_dashboard.py}
→ blocked: {config/, samuel/core/, samuel/adapters/}
```

**Sprachen:** Sprachagnostisch — reine Pfad-Metadaten.

**Geht an:** K6 (Expansion-Filter), K9 (Grep-Filter), K11 (module_context-Sektion im Prompt).

**Voraussetzungen:** `config/architecture.json` existiert. Wenn nicht: Pipeline läuft ohne Arch-Constraints (degraded mode).

---

## K6 — `expand_via_symbol_references()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Sprachagnostische Erweiterung der Plan-Files: wenn Plan-File A ein Symbol referenziert, das in File B definiert ist, füge B hinzu.

**Ersetzt v1-Python-only `expand_via_imports` (AST-basiert).**

**Algorithmus:**
1. Baue **Skeleton-Index:** `{symbol_name: [file1, file2]}` über alle Builder (K7)
2. Für jede Plan-File:
   - Lies Inhalt (nur wenn Extension in `CODE_EXTENSIONS | CONFIG_EXTENSIONS`)
   - Extrahiere alle Identifier (Regex `[A-Za-z_][A-Za-z0-9_]{3,}`)
   - Für jedes Identifier: lookup im Index
3. Filter:
   - **Ambiguous-Filter:** Symbol in >1 Files → skip (außer lang genug: ≥6 chars und ≤2 Defs)
   - **Test-Skip:** Tests/Fixtures werden nicht erweitert (außer Quelle ist selbst Test)
   - **Arch-Scope:** blocked/allowed greifen (K5)
4. Max 8 neue Files

**Doc-File-Skip:** README.md/*.txt triggern keine Expansion (würde auf jede Code-Tokens matchen).

**Beispiel:**
```
Plan-Files: samuel/cli.py

cli.py referenziert:
  main                 → definiert in: cli.py (self, skip)
  bootstrap            → definiert in: samuel/core/bootstrap.py [1 Def] → ADD
  ImplementCommand     → definiert in: samuel/core/commands.py [1 Def] → ADD
  handle               → definiert in: 15+ Slices [ambiguous, 4 chars] → SKIP
  register             → definiert in: 5+ Slices [ambiguous] → SKIP

Result: cli.py + bootstrap.py + commands.py
```

**Sprachen:** Alle, die einen `ISkeletonBuilder` haben (K7). Kein Parser-spezifischer Code.

**Voraussetzungen:** Mindestens 1 Skeleton-Builder für die Plan-File-Sprache.

**Geht an:** K8 (filter_skeleton), K10 (render_files_section).

---

## K7 — Skeleton-Builders

**Dateien:**
- Port: `samuel/core/ports.py` → `ISkeletonBuilder`
- Registry: `samuel/adapters/skeleton/registry.py` → `SKELETON_BUILDERS: dict[ext, builder]`
- Implementierungen: `samuel/adapters/skeleton/{python_ast, tree_sitter_ts, tree_sitter_go, sql_builder, config_builder}.py`

**Zweck:** Extrahiert Symbol-Struktur (Funktionen, Klassen, Methoden, Module-Variables, Config-Keys) aus Dateien — sprach-spezifisch.

**Interface:**
```python
class ISkeletonBuilder(ABC):
    supported_extensions: set[str]
    @abstractmethod
    def extract(self, file: Path) -> list[SkeletonEntry]: ...
```

**SkeletonEntry:**
```python
@dataclass
class SkeletonEntry:
    name: str
    kind: str           # "function", "class", "method", "variable", "key", "type", ...
    file: str
    line_start: int
    line_end: int
    calls: list[str]      = []
    called_by: list[str]  = []
    language: str         = ""
```

**Registrierte Builders:**

| Ext | Builder | Kind-Werte |
|---|---|---|
| `.py` | `PythonASTBuilder` (AST) | function, class, method, variable |
| `.ts/.tsx/.js/.jsx` | `TreeSitterTSBuilder` | function, class, method, interface, type |
| `.go` | `GoRegexBuilder` | function, method (`Struct.Method`), struct |
| `.sql` | `SQLBuilder` | view, procedure, index |
| `.json/.yaml/.yml/.toml` | `StructuredConfigBuilder` | key |

**Fallback-Verhalten:**
- Python: AST falls kein Tree-sitter → immer verfügbar (stdlib)
- TS/JS: Tree-sitter (optional pip install `tree_sitter_typescript`); ohne Tree-sitter: leere Liste
- Go: Regex-basiert (keine externe Abhängigkeit)

**Dedup-Bug-Fix (Phase 14.9):**
Die Registry hat `StructuredConfigBuilder` für 4 Extensions mit gleicher Instance. `filter_skeleton` / `_build_symbol_index` deduplizieren via `id(builder)`.

**Beispiele:**

Python:
```python
# input: mod.py
def calculate_total(items): ...  # L2
class ShoppingCart:              # L5
    def __init__(self): ...
    def add_item(self, x): ...
CART_MAX_SIZE = 100              # L11

# output:
[
  SkeletonEntry("calculate_total", "function", "mod.py", 2, 3),
  SkeletonEntry("ShoppingCart", "class", "mod.py", 5, 9),
  SkeletonEntry("add_item", "function", "mod.py", 8, 9),
  SkeletonEntry("CART_MAX_SIZE", "variable", "mod.py", 11, 11),
]
```

TypeScript:
```typescript
// input: mod.ts
export class User {
  greet(): string { ... }   // L3
}
```
```
→ SkeletonEntry("User", "class", "mod.ts", 1, 4)
→ SkeletonEntry("User.greet", "method", "mod.ts", 3, 3)  (qualifiziert!)
```

JSON:
```json
// input: agent.json
{"log_level": "INFO", "mode": "standard"}
```
```
→ SkeletonEntry("log_level", "key", "agent.json", 1, 1)
→ SkeletonEntry("mode", "key", "agent.json", 1, 1)
```

**Wer nutzt das?** K6 (Symbol-Index für Expansion), K8 (filter_skeleton).

**Voraussetzungen pro Builder:**
- Python AST: stdlib (immer OK)
- Tree-sitter: optional `pip install tree_sitter tree_sitter_typescript`
- Go: stdlib Regex
- Config: stdlib `json`, optional `pyyaml`

---

## K8 — `filter_skeleton()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Findet Skeleton-Symbole die im Issue-Text vorkommen (umgekehrtes Matching, v1-Style). Liefert Kontext-Sektion "Repo-Skeleton" mit Zeilennummern.

**Algorithmus:**
1. Extrahiere Backticks aus Issue-Text: `` `symbol_name` `` → Set
2. Extrahiere alle Identifier aus Issue-Text: Regex `[A-Za-z_][A-Za-z0-9_]{3,}` → Set
3. Scan Projekt mit allen Buildern (deduped via `id()`):
   - Für jeden Eintrag: prüfe ob `entry.name` in Backticks (Score +5) oder all_tokens (Score +3)
   - Plan-File-Bonus: +4 wenn Datei in `plan_files`
   - Magic-Name-Filter: `__init__`, `__main__`, etc. werden gefiltert (außer Backtick oder Plan-File)
4. Sortiere nach Score
5. Max 60 Matches (`max_entries`)

**Score-Tabelle:**
| Match-Typ | Score |
|---|---|
| Symbol in Backticks | +5 |
| Symbol als Token im Issue | +3 |
| Datei ist Plan-File | +4 |
| (kumulativ, max 12) | |

**Beispiel:**
```
Issue: "Füge `__version__` in `samuel/cli.py` ein."

Skeleton-Scan findet:
  __version__ in samuel/__init__.py    → Backtick (+5), ist plan_file (+4) = 9
  _cmd_run in samuel/cli.py            → Token (+3), ist plan_file (+4) = 7
  bootstrap in samuel/core/bootstrap.py→ Token (+3) = 3

Ergebnis sortiert: __version__ (9), _cmd_run (7), bootstrap (3)
```

**Sprachen:** Sprachagnostisch — aggregiert Outputs aller registrierten Builder.

**Output:** `list[tuple[str, SkeletonEntry]]` — Pairs von (rel_path, entry)

**Rendering (`render_skeleton_section`):**
```markdown
## Repo-Skeleton (keyword-gefiltert, mit Zeilennummern)

### samuel/__init__.py
- **variable** `__version__` Zeilen 1-1

### samuel/cli.py
- **function** `_cmd_run` Zeilen 84-100
```

**Geht an:** K10 (Region-Anker), K11 (Prompt-Sektion).

---

## K9 — `grep_keywords()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Findet Code-Zeilen die Keywords aus K3 enthalten. Liefert zusätzliche Orientierung für den LLM, ergänzt das Skeleton.

**Algorithmus:**
1. Kompiliere Regex `\b{keyword}\b` (Word-Boundary, case-insensitive) pro Keyword
2. Scan Projekt via `iter_project_files` mit `CODE_EXTENSIONS`
3. Respektiert Arch-Scope (`allowed` / `blocked`) — wichtig!
4. Max 5 Hits pro Keyword (`max_hits_per_keyword`)
5. Top-5 Keywords aus K3 (`keywords[:5]`)

**Word-Boundary-Fix:** Ohne `\b` matched "cli" auch "click" → früher massiv Noise (HTML class-Namen). Fix in Phase 14.8.

**Scope-Filter:** Seit Phase 14.10 — Grep überspringt Files in `blocked_scopes`.

**Beispiel:**
```
Keywords: ["health", "status", "dashboard"]
Arch-allowed: {samuel/server.py, samuel/slices/dashboard/, tests/test_server_dashboard.py}

Grep findet:
  samuel/server.py:46 — .health-row{display:flex;...}
  samuel/server.py:107 — <div class="card"><h3>Health</h3>...
  samuel/server.py:93 — <button class="tab" onclick="showTab('status')">
  samuel/slices/dashboard/handler.py:40 — def get_status(self):
  ...
```

**Rendering (`render_grep_section`):**
```markdown
## Keyword-Vorkommen im Projekt (Grep)

### `health`
- samuel/server.py:46 — `.health-row{display:flex;...}`
- samuel/server.py:107 — `<div class="card"><h3>Health</h3>...`

### `status`
- ...
```

**Sprachen:** Alle via `CODE_EXTENSIONS` (keyword-suche, keine Sprach-Parser).

**Geht an:** K10 (Region-Anker für Files ohne Skeleton-Match), K11 (Prompt-Sektion).

---

## K10 — `render_files_section()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Lädt Datei-Inhalte in den Prompt — aber **smart**: nur relevante Regionen, nicht komplette Files.

**Entscheidungs-Baum pro File:**

```
Datei exists?
├─ Nein → skip
└─ Ja
   ├─ total ≤ 150 Zeilen (SMALL_FILE_THRESHOLD_LINES)
   │  └─ komplett laden (mit Zeilennummern)
   ├─ Skeleton-Matches für diese Datei (aus K8) ?
   │  └─ Ja: Regions aus Matches ± 10 Zeilen (REGION_CONTEXT_LINES), merged
   ├─ Grep-Hits für diese Datei (aus K9) ?
   │  └─ Ja: Hit-Lines ± 10 Zeilen als Regions
   └─ total > 300 Zeilen (FALLBACK_TOC_THRESHOLD)
      ├─ Ja: nur Hinweis "Datei zu groß, kein Anker — Skeleton siehe oben"
      └─ Nein: erste `max_lines` (600) Zeilen (Fallback)
```

**Rendering mit Zeilennummern:**
```markdown
## Relevante Dateien (aus Plan)

### samuel/server.py (648 Zeilen)

_(Zeilen 3-34 von 648)_
​```
    3 | import json
    4 | import logging
    ...
​```

_(Zeilen 83-120 von 648)_
​```
   83 | <div class="tab-content" id="tab-status">
   ...
​```
```

**Merge-Regel:** Überlappende oder benachbarte Regionen werden zu einem Block zusammengefasst (`_merge_ranges`).

**Konstanten:**
| Name | Wert | Bedeutung |
|---|---|---|
| `SMALL_FILE_THRESHOLD_LINES` | 150 | darunter: immer komplett |
| `REGION_CONTEXT_LINES` | 10 | ± um Match-Region |
| `FALLBACK_TOC_THRESHOLD` | 300 | darüber: kein Blind-Load |
| `MAX_RELEVANT_FILE_LINES` | 600 | max Fallback-Fenster |

**Beispiel (server.py 648 Zeilen für Dashboard-Issue):**
- Skeleton-Match: 0 (keine Symbolnamen im Issue)
- Grep-Hits: 5+ (`health`, `status`, `dashboard`)
- → 6 Regions mit insg. ~200 Zeilen (statt 648)

**Sprachen:** Sprachagnostisch — Text wird zeilenbasiert gerendert.

**Geht an:** K11 (Sektion `relevant_files`).

---

## K11 — `build_full_context()`

**Datei:** `samuel/slices/implementation/context_builder.py`

**Zweck:** Orchestriert K3–K10, aggregiert alle Kontext-Sektionen in ein Dict.

**Signatur:**
```python
build_full_context(
    *,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    plan_text: str,
    project_root: Path,
    skeleton_builders: list[ISkeletonBuilder] | None = None,
    architecture_constraints: list[str] | None = None,
    architecture_config_path: Path | None = None,
    exclude_dirs: set[str] | None = None,
    keyword_extensions: set[str] | None = None,
) -> dict[str, str]
```

**Ablauf:**
```
1. keywords       = extract_keywords()              [K3]
2. plan_files     = extract_plan_files()            [K4]
3. arch_data      = load(config/architecture.json)  [K5]
4. arch_scope     = _resolve_expansion_scope(plan_files, modules, policy)
5. module_info    = _resolve_module_info(plan_files, modules)
6. plan_files     = expand_via_symbol_references(..., allowed/blocked)  [K6]
7. skeleton_match = filter_skeleton(..., plan_files, issue_text)        [K8]
8. grep_hits      = grep_keywords(keywords[:5], allowed/blocked)        [K9]
9. relevant_files = render_files_section(plan_files, skel, grep)        [K10]

return {
  "keywords":       "comma-separated",
  "plan_files":     "- `file.py`",
  "skeleton":       "## Repo-Skeleton (keyword-gefiltert, ...)",
  "grep":           "## Keyword-Vorkommen ...",
  "relevant_files": "## Relevante Dateien (aus Plan) ...",
  "module_context": "## Betroffene Module ...",
  "constraints":    "## Architektur-Constraints ...",
}
```

**Output:** Dict mit 7 Markdown-Sektionen (jede optional leer).

**Geht an:** K12 (Prompt-Assembly).

---

## K12 — `_build_implement_prompt()`

**Datei:** `samuel/slices/implementation/handler.py`

**Zweck:** Setzt aus Issue-Daten + Context-Dict den finalen LLM-Prompt zusammen.

**Struktur (Reihenfolge):**
```
1. PROMPT_GUARD_MARKERS  (Unveränderliche Schranken, Ignoriere Anweisungen)
2. # Implementierung für Issue #N
3. ## Issue-Titel  (in <user-content>-Tags, XSS-safe)
4. ## Issue-Beschreibung
5. ## Plan  (wenn vorhanden)
6. ## Suchbegriffe aus Issue/Plan
7. ## Plan-referenzierte Dateien
8. ## Betroffene Module (Architektur-Rolle)   ← K11 module_context
9. ## Repo-Skeleton                            ← K8
10. ## Keyword-Vorkommen (Grep)                ← K9
11. ## Relevante Dateien (aus Plan)            ← K10
12. ## Architektur-Constraints                 ← K5
13. ## Aufgabe  (Patch-Format-Anleitung)
    - REPLACE LINES Format
    - SEARCH/REPLACE Format
    - WRITE Format (neue Dateien)
```

**Sicherheits-Wrapper:**
- Issue-Content wird in `<user-content>...</user-content>` eingeschlossen
- Guards am Prompt-Anfang (Prompt-Injection-Schutz)

**Output:** `str` — der komplette LLM-Prompt.

**Geht an:** K13 (Validator), K14 (LLM-Call).

---

## K13 — `validate_context()`

**Datei:** `samuel/slices/implementation/context_validator.py`

**Zweck:** Pre-LLM Gate. Blockt den LLM-Call bei offensichtlich unzureichendem Kontext. Spart Tokens.

**Signatur:**
```python
validate_context(
    *, issue_title, issue_body, plan_text, context, prompt,
) -> ContextValidation
```

**Checks:**

| Check | Resultat | Schwelle |
|---|---|---|
| Issue-Title leer | BLOCK | - |
| Issue-Body < 20 chars | BLOCK | - |
| Kein Skeleton AND kein Plan-File AND kein Relevant-File AND kein Grep | BLOCK | - |
| Kein Plan-File AND kein Relevant-File | WARN | - |
| Kein Plan-Text | WARN | - |
| Prompt < 200 Tokens | BLOCK | `MIN_PROMPT_TOKENS` |
| Prompt > 80_000 Tokens | BLOCK | `MAX_PROMPT_TOKENS` |
| Prompt > 30_000 Tokens | WARN | `WARN_PROMPT_TOKENS` |

**Output (`ContextValidation`):**
```python
@dataclass
class ContextValidation:
    ok: bool
    issues: list[str]      # Blocker
    warnings: list[str]    # Advisories
    prompt_tokens_est: int
    breakdown: dict[str, int]  # chars pro Sektion
```

**Bypass:** Im Handler per `enforce_context_quality=False` (Tests).

**Beispiel — OK:**
```
prompt_tokens_est: 7706
issues: []
warnings: []
breakdown: {skeleton: 775, relevant_files: 25262, ...}
→ ok=True → LLM-Call startet
```

**Beispiel — BLOCK:**
```
issues: [
  "Issue body too short (3 chars)",
  "No code context found at all",
  "Prompt too small (174 tokens)"
]
→ ok=False → WorkflowBlocked-Event, kein LLM-Call
```

**Geht an:** K14 (wenn OK) oder `WorkflowBlocked`-Event (wenn BLOCK).

---

## K14 — `run_llm_loop()`

**Datei:** `samuel/slices/implementation/llm_loop.py`

**Zweck:** Iterativer LLM-Call mit Patch-Anwendung und Retry-mit-echtem-Code bei Fehlern.

**Schleife:**
```
MAX_ROUNDS = 5

for round in 1..5:
    response = llm.complete([{"role": "user", "content": current_prompt}])
    
    if response.stop_reason == "max_tokens":
        return {"reason": "token_limit"}
    
    patches = parse_patches(response.text)
    if not patches:
        break
    
    for patch in patches:
        apply(patch) → (ok, msg)
        if ok: patches_applied += patch
        else:  round_failures += (msg, patch)
    
    if no round_failures:
        break
    
    current_prompt = build_retry_prompt(
        base_prompt, round_num, failures_with_patches, project_root,
    )
    # Retry lädt echten Quellcode der gescheiterten Files!
```

**Retry-Prompt (Kern-Feature Phase 14.4):**
```
[Original-Prompt]

## Patch-Fehler in Runde N — KORRIGIEREN
- SEARCH not found in cli.py
- line range 50-60 out of bounds ...

## Aktueller Quellcode der betroffenen Dateien
### cli.py (aktueller Zustand)
​```
   42 | def _build_parser():
   43 |     p = argparse.ArgumentParser(...)
   ...
​```
```

**Code-Anker bei Fehler:**
- `replace_lines` Patch: ± 10 Zeilen um die Zielrange
- `search_replace` Patch: finde erste Zeile im File, ± 10 Zeilen
- unbekannt: erste 200 Zeilen

**Output:**
```python
{
    "success": bool,
    "reason": "complete" | "partial_failure" | "token_limit",
    "round": int,
    "patches_applied": list[dict],
    "failures": list[str],
    "input_tokens": int,
    "output_tokens": int,
}
```

**Sprachen:** Sprachagnostisch — Patch-Parser + Retry sind Format-basiert, nicht Sprach-basiert.

**Geht an:** K15 (Patches zum Anwenden) — Anwendung passiert eigentlich inline in K14, K15 ist nur der Applier.

---

## K15 — `patch_parser` + Applier

**Datei:** `samuel/slices/implementation/patch_parser.py`

**Zweck:** Parst LLM-Response zu Patches und wendet sie auf das Filesystem an.

**Unterstützte Formate (drei):**

### REPLACE LINES (bevorzugt, v1-Style)
```
## datei.py
REPLACE LINES 10-25
[neuer Code]
END REPLACE
```

### SEARCH/REPLACE
```
## datei.py
<<<<<<< SEARCH
[alter Code exakt]
=======
[neuer Code]
>>>>>>> REPLACE
```

### WRITE (neue Datei)
```
## WRITE: neue_datei.py
[kompletter Inhalt]
## END_WRITE
```

**Applier-Klassen:**
- `LinePatchApplier` (default für alle Extensions)
- `JSONPatchApplier` (validiert JSON nach Patch)
- `YAMLPatchApplier` (stub — LinePatch + YAML-Validate-Passthrough)

**Python-Validate:** `LinePatchApplier.validate()` nutzt `ast.parse()` für `.py` Files → syntax-Fehler werden erkannt.

**Output:** `list[tuple[bool, str]]` — (applied, message)

**Sprachen:** Sprachagnostisch. Python-spezifisch: syntax-validation nach Patch.

**Geht an:** K16 (bei success → git commit), sonst Retry (K14).

---

## K16 — Git-Operationen + `CodeGenerated`-Event

**Dateien:**
- `samuel/core/git.py` — Git-Adapter (stdlib subprocess)
- `samuel/slices/implementation/handler.py` — orchestriert

**Zweck:** Sichert das LLM-Ergebnis in einem Git-Branch, publiziert `CodeGenerated`-Event.

**Ablauf (nur wenn `result["success"]`):**
```python
branch_name = f"samuel/issue-{issue_number}"

_git.create_branch(branch_name, "main", cwd=project)
_git.stage_files([], cwd=project)   # stage all
_git.commit(
    f"feat: Issue #{N} — LLM-generierte Implementierung\n\n"
    f"Patches: {len(patches)}\n"
    f"Rounds: {round}\n"
    f"AI-Generated-By: S.A.M.U.E.L.@v2",
    cwd=project,
)
_git.push(branch_name, cwd=project)
_git.checkout("main", cwd=project)

bus.publish(CodeGenerated(payload={
    "issue": issue_number,
    "patches_applied": len(patches),
    "rounds": round,
    "branch": branch_name,
}))
```

**Ausgelöste Folge-Events (Workflow-Engine):**
- `CodeGenerated` → `Evaluate` Command → `EvalCompleted` → `CreatePR` Command → `PRCreated`
- PR-Gates laufen in `samuel/slices/pr_gates/handler.py`

**Voraussetzungen:**
- Git installiert, Repo initialisiert
- Push-Remote konfiguriert (`SCM_URL`, `SCM_TOKEN`, `SCM_REPO`)
- Main-Branch existiert

---

## Anhang: Config-Dateien

Folgende Config-Dateien steuern die Pipeline (alle unter `config/`):

| Datei | Zweck | K-Nodes |
|---|---|---|
| `agent.json` | Exclude-Dirs, max_file_size_kb, mode, self_mode | K2, K11 |
| `architecture.json` | Rollen + Scopes + Constraints | K5, K11 |
| `features.json` | Feature-Flags (hallucination_guard, sequence_validator, ...) | K14 indirekt |
| `llm.json` / `llm/*.json` | LLM-Provider + Routing | K14 |
| `gates.json` | Pre-PR Gates | K16 Folge |
| `labels.json` | Workflow-Labels (Phase 14.1) | K16 Folge |

### Beispiel `config/agent.json`:
```json
{
  "mode": "standard",
  "context": {
    "max_file_size_kb": 50,
    "exclude_dirs": ["__pycache__", ".git", ...],
    "keyword_extensions": [".py", ".js", ".ts", ...]
  }
}
```

### Beispiel `config/architecture.json`:
(siehe K5 oben — definiert Module + Rollen + expansion_policy)

---

## Pipeline-Lesetipps für verschiedene Personas

**Neue Entwickler:** Lies K1 → K11 → K12 → K14 in dieser Reihenfolge.

**Für Debugging eines schlechten Prompts:**
Starte bei K13 (Validator-Output), dann rückwärts über K11 zu K4/K3/K5.

**Für neue Sprach-Unterstützung:**
1. Implementiere neuen `ISkeletonBuilder` (K7)
2. Registriere in `samuel/adapters/skeleton/registry.py`
3. Test: K3 extrahiert Keywords (bereits sprachagnostisch), K6 findet Symbole, K10 rendert Files

**Für neue Projekt-Architektur:**
Passe `config/architecture.json` an (K5) — keine Code-Änderung nötig.

---

*Dokument erstellt: 2026-04-17, Stand Phase 14.11 (PR #154).*
*Bei Pipeline-Änderungen dieses Dokument mitpflegen.*
