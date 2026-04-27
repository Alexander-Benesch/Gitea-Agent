from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from samuel.core.ports import ISkeletonBuilder
from samuel.core.project_files import iter_project_files
from samuel.core.types import SkeletonEntry

log = logging.getLogger(__name__)

_STOP_WORDS = {
    # English
    "issue", "ticket", "task", "plan", "code", "file", "test", "tests",
    "please", "this", "that", "with", "from", "into", "when", "then",
    "should", "must", "implement", "will", "can", "new", "all", "any",
    "the", "and", "for", "not", "but", "are", "was", "were", "have", "has",
    "does", "did", "per", "via", "add", "need", "needs", "use", "used",
    "also", "just", "make", "want",
    # German
    "soll", "sollen", "muss", "müssen", "kann", "können", "wird", "werden",
    "ist", "sind", "bitte", "hier", "jetzt", "wenn", "dann", "sonst",
    "neu", "neue", "neuer", "neues", "alle", "alles", "eine", "einen", "einer",
    "ein", "eines", "dies", "diese", "dieser", "dieses",
    "aufgabe", "ziel", "context", "kontext", "beschreibung",
    "gibt", "aus", "der", "die", "das", "den", "dem", "des",
    "und", "oder", "als", "auf", "bei", "beim", "von", "vom", "zur", "zum",
    "mit", "ohne", "für", "gegen", "ueber", "über", "unter", "nach", "vor",
    "weiter", "zuerst", "ersten", "letzten",
    "implementierung", "implementierte", "umsetzung",
    "genügt", "genug", "aktuell", "bereits", "wurde", "wurden", "gelesen",
    # Generic/magic
    "__init__", "__main__", "python", "samuel",
}

_KEYWORD_PATTERN = re.compile(r"[A-Za-z_][\w]{2,}", re.UNICODE)
_FILE_PATTERN = re.compile(
    r"(?:^|[\s`'\"])([a-zA-Z0-9_/.-]+(?:\.[a-zA-Z]{1,5}))(?=[\s`'\":,)]|$)",
    re.MULTILINE,
)

MAX_KEYWORDS = 12
MAX_GREP_HITS_PER_KEYWORD = 5
MAX_RELEVANT_FILE_LINES = 600
MAX_RELEVANT_FILES = 8


def extract_keywords(*texts: str, limit: int = MAX_KEYWORDS) -> list[str]:
    seen: dict[str, int] = {}
    for text in texts:
        if not text:
            continue
        for match in _KEYWORD_PATTERN.findall(text):
            low = match.lower()
            if low in _STOP_WORDS:
                continue
            if low in seen:
                seen[low] += 1
            else:
                seen[low] = 1
    return [kw for kw, _ in sorted(seen.items(), key=lambda x: (-x[1], x[0]))[:limit]]


def extract_plan_files(text: str, project_root: Path) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for match in _FILE_PATTERN.finditer(text):
        candidate = match.group(1).strip()
        if candidate.startswith(("/", "http", "./")) or ".." in candidate:
            continue
        if len(candidate) > 200:
            continue
        if (project_root / candidate).exists():
            if candidate not in found:
                found.append(candidate)
    return found[:MAX_RELEVANT_FILES]


_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def _build_symbol_index(
    builders: list[ISkeletonBuilder],
    project_root: Path,
    *,
    exclude_dirs: set[str] | None = None,
    min_symbol_len: int = 4,
) -> dict[str, list[str]]:
    """Map symbol-name -> list of relative file paths where symbol is defined.

    Sprach-agnostisch via registered ISkeletonBuilder.
    """
    index: dict[str, list[str]] = {}
    root_resolved = project_root.resolve()
    seen_builders: set[int] = set()
    for builder in builders:
        if id(builder) in seen_builders:
            continue
        seen_builders.add(id(builder))
        for f in iter_project_files(
            project_root,
            extensions=builder.supported_extensions,
            max_size_kb=50,
            exclude_dirs=exclude_dirs,
        ):
            try:
                entries = builder.extract(f)
            except Exception:
                continue
            rel = str(f.relative_to(root_resolved))
            for entry in entries:
                name = str(entry.name)
                if len(name) < min_symbol_len:
                    continue
                if name in _NOISE_MAGIC_NAMES:
                    continue
                index.setdefault(name, [])
                if rel not in index[name]:
                    index[name].append(rel)
    return index


_MAX_AMBIGUOUS_DEFS = 1
_MIN_UNAMBIGUOUS_SYMBOL_LEN = 6


def _in_any_scope(path: str, scopes: set[str]) -> bool:
    for scope in scopes:
        if scope.endswith("/"):
            if path.startswith(scope):
                return True
        elif path == scope or path.startswith(scope + "/"):
            return True
    return False


def expand_via_symbol_references(
    files: list[str],
    project_root: Path,
    *,
    builders: list[ISkeletonBuilder] | None = None,
    exclude_dirs: set[str] | None = None,
    max_added: int = MAX_RELEVANT_FILES,
    allowed_scopes: set[str] | None = None,
    blocked_scopes: set[str] | None = None,
) -> list[str]:
    """Expand plan-files by finding referenced symbols that are defined elsewhere.

    Sprach-agnostisch: Liest jede plan-file als Text, extrahiert alle
    Identifier (regex), sucht sie im Skeleton-Index aller anderen Files.
    Wenn ein Symbol in file B definiert ist und in plan-file A referenziert wird,
    wird B als relevant eingestuft.

    Ambiguous symbols (>3 Definitionen, z.B. Interface-Methoden) werden übersprungen.
    Test-Fixture-Pfade werden nachgelagert sortiert.
    """
    if not builders:
        return list(files)

    expanded: list[str] = list(files)
    seen = set(files)
    candidates: list[tuple[int, str]] = []

    index = _build_symbol_index(builders, project_root, exclude_dirs=exclude_dirs)

    from samuel.core.project_files import CODE_EXTENSIONS, CONFIG_EXTENSIONS
    scan_exts = CODE_EXTENSIONS | CONFIG_EXTENSIONS

    for rel in files:
        full = project_root / rel
        if not full.exists() or not full.is_file():
            continue
        if full.suffix not in scan_exts:
            # Doc-Files (.md/.txt/...) triggern keine Symbol-Expansion
            continue
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        referenced = set(_IDENTIFIER_PATTERN.findall(content))
        for sym in referenced:
            defs = index.get(sym)
            if not defs:
                continue
            # Ambiguous symbols only propagate if they're long enough (rare, specific)
            if len(defs) > _MAX_AMBIGUOUS_DEFS and len(sym) < _MIN_UNAMBIGUOUS_SYMBOL_LEN:
                continue
            if len(defs) > _MAX_AMBIGUOUS_DEFS * 2:  # cap hard
                continue
            for target_rel in defs:
                if target_rel == rel or target_rel in seen:
                    continue
                # Skip test/fixture paths unless plan-file itself is a test
                src_is_test = "tests/" in rel or "/test_" in rel or "fixtures/" in rel
                tgt_is_test = "tests/" in target_rel or "/test_" in target_rel or "fixtures/" in target_rel
                if tgt_is_test and not src_is_test:
                    continue
                if blocked_scopes and _in_any_scope(target_rel, blocked_scopes):
                    continue
                if allowed_scopes and not _in_any_scope(target_rel, allowed_scopes):
                    continue
                candidates.append((0, target_rel))
                seen.add(target_rel)

    candidates.sort(key=lambda c: (c[0], c[1]))
    for _, target_rel in candidates[:max_added]:
        expanded.append(target_rel)
    return expanded




_BACKTICK_PATTERN = re.compile(r"`([^`\n]{3,80})`")
_SYMBOL_MIN_LEN = 4
_NOISE_MAGIC_NAMES = {"__init__", "__main__", "__new__", "__repr__", "__str__",
                       "__call__", "__eq__", "__hash__", "__enter__", "__exit__",
                       "__iter__", "__next__", "__len__", "__getitem__", "__setitem__",
                       "__contains__", "__del__"}


def _symbols_in_text(text: str) -> tuple[set[str], set[str]]:
    backticks: set[str] = set()
    for m in _BACKTICK_PATTERN.finditer(text or ""):
        term = m.group(1).strip()
        if len(term) >= _SYMBOL_MIN_LEN:
            backticks.add(term)
    all_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text or ""))
    return backticks, all_tokens


def filter_skeleton(
    builders: list[ISkeletonBuilder],
    project_root: Path,
    *,
    issue_text: str = "",
    plan_files: list[str] | None = None,
    exclude_dirs: set[str] | None = None,
    max_file_size_kb: int = 20,
    max_entries: int = 60,
) -> list[tuple[str, SkeletonEntry]]:
    if not builders:
        return []

    plan_file_set = set(plan_files or [])
    root_resolved = project_root.resolve()

    backticks, all_tokens = _symbols_in_text(issue_text)
    matches: list[tuple[str, SkeletonEntry, int]] = []
    seen_builders: set[int] = set()

    for builder in builders:
        if id(builder) in seen_builders:
            continue
        seen_builders.add(id(builder))
        for f in iter_project_files(
            project_root,
            extensions=builder.supported_extensions,
            max_size_kb=max_file_size_kb,
            exclude_dirs=exclude_dirs,
        ):
            try:
                entries = builder.extract(f)
            except Exception:
                continue

            rel = str(f.relative_to(root_resolved))
            is_plan_file = rel in plan_file_set

            for entry in entries:
                name = str(entry.name)
                score = 0
                if len(name) < _SYMBOL_MIN_LEN and not is_plan_file:
                    continue
                if name in _NOISE_MAGIC_NAMES and name not in backticks and not is_plan_file:
                    continue
                if name in backticks:
                    score += 5
                if name in all_tokens:
                    score += 3
                if is_plan_file:
                    score += 4
                if score > 0:
                    matches.append((rel, entry, score))

    matches.sort(key=lambda m: (-m[2], m[0], m[1].line_start))
    return [(rel, entry) for rel, entry, _ in matches[:max_entries]]


def grep_keywords(
    project_root: Path,
    keywords: list[str],
    *,
    extensions: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    max_hits_per_keyword: int = MAX_GREP_HITS_PER_KEYWORD,
    allowed_scopes: set[str] | None = None,
    blocked_scopes: set[str] | None = None,
) -> dict[str, list[tuple[str, int, str]]]:
    if not keywords:
        return {}

    from samuel.core.project_files import CODE_EXTENSIONS
    exts = extensions or CODE_EXTENSIONS
    hits: dict[str, list[tuple[str, int, str]]] = {kw: [] for kw in keywords}
    patterns: dict[str, re.Pattern[str]] = {
        kw: re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in keywords
    }
    root_resolved = project_root.resolve()

    for f in iter_project_files(project_root, extensions=exts, exclude_dirs=exclude_dirs):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        rel = str(f.relative_to(root_resolved))
        if blocked_scopes and _in_any_scope(rel, blocked_scopes):
            continue
        if allowed_scopes and not _in_any_scope(rel, allowed_scopes):
            continue
        for lineno, line in enumerate(lines, start=1):
            for kw in keywords:
                if len(hits[kw]) >= max_hits_per_keyword:
                    continue
                if patterns[kw].search(line):
                    hits[kw].append((rel, lineno, line.strip()[:200]))

    return {kw: hs for kw, hs in hits.items() if hs}


def load_file_excerpt(
    project_root: Path,
    rel_path: str,
    *,
    start: int = 0,
    end: int = 0,
    max_lines: int = MAX_RELEVANT_FILE_LINES,
) -> str:
    full = project_root / rel_path
    if not full.exists() or not full.is_file():
        return ""
    try:
        lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    if start > 0 and end > 0:
        start_idx = max(0, start - 1)
        end_idx = min(len(lines), end)
    else:
        start_idx = 0
        end_idx = min(len(lines), max_lines)
    return "\n".join(
        f"{i+1:5d} | {lines[i]}" for i in range(start_idx, end_idx)
    )


def render_skeleton_section(matches: list[tuple[str, SkeletonEntry]]) -> str:
    if not matches:
        return ""
    lines = ["## Repo-Skeleton (keyword-gefiltert, mit Zeilennummern)"]
    by_file: dict[str, list[SkeletonEntry]] = {}
    for rel, entry in matches:
        by_file.setdefault(rel, []).append(entry)
    for rel in sorted(by_file):
        lines.append(f"\n### {rel}")
        for e in by_file[rel]:
            lines.append(f"- **{e.kind}** `{e.name}` Zeilen {e.line_start}-{e.line_end}")
    return "\n".join(lines)


def render_grep_section(hits: dict[str, list[tuple[str, int, str]]]) -> str:
    if not hits:
        return ""
    lines = ["## Keyword-Vorkommen im Projekt (Grep)"]
    for kw, items in hits.items():
        lines.append(f"\n### `{kw}`")
        for rel, lineno, text in items:
            lines.append(f"- {rel}:{lineno} — `{text}`")
    return "\n".join(lines)


SMALL_FILE_THRESHOLD_LINES = 150
REGION_CONTEXT_LINES = 10
FALLBACK_TOC_THRESHOLD = 300


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    sorted_r = sorted(ranges)
    merged = [sorted_r[0]]
    for s, e in sorted_r[1:]:
        ls, le = merged[-1]
        if s <= le + 1:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def render_files_section(
    project_root: Path,
    files: list[str],
    *,
    max_lines: int = MAX_RELEVANT_FILE_LINES,
    skeleton_matches: list[tuple[str, SkeletonEntry]] | None = None,
    grep_hits: dict[str, list[tuple[str, int, str]]] | None = None,
) -> str:
    """Rendert die Relevant-Files-Section.

    Strategie:
    - Kleine Files (< SMALL_FILE_THRESHOLD_LINES): komplett
    - Große Files mit Skeleton-Matches: Match-Regions + ±REGION_CONTEXT_LINES
    - Große Files ohne Skeleton-Matches aber mit Grep-Hits: Hit-Zeilen als Anker
    - Große Files ohne jeden Anker: Header (erste N Zeilen als Fallback)
    """
    if not files:
        return ""

    regions_by_file: dict[str, list[tuple[int, int]]] = {}
    if skeleton_matches:
        for rel, entry in skeleton_matches:
            if rel in files:
                regions_by_file.setdefault(rel, []).append(
                    (entry.line_start, entry.line_end)
                )
    grep_linenos: dict[str, list[int]] = {}
    if grep_hits:
        for _kw, hits in grep_hits.items():
            for rel, lineno, _text in hits:
                if rel in files:
                    grep_linenos.setdefault(rel, []).append(lineno)

    lines = ["## Relevante Dateien (aus Plan)"]
    for rel in files:
        full = project_root / rel
        if not full.exists() or not full.is_file():
            continue
        try:
            file_lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        total = len(file_lines)
        lines.append(f"\n### {rel} ({total} Zeilen)")

        if total <= SMALL_FILE_THRESHOLD_LINES:
            lines.append("```")
            lines.append("\n".join(f"{i:5d} | {file_lines[i-1]}" for i in range(1, total + 1)))
            lines.append("```")
            continue

        regions = list(regions_by_file.get(rel, []))
        if not regions and grep_linenos.get(rel):
            regions = [(ln, ln) for ln in grep_linenos[rel]]

        if regions:
            expanded = [
                (max(1, s - REGION_CONTEXT_LINES), min(total, e + REGION_CONTEXT_LINES))
                for s, e in regions
            ]
            merged = _merge_ranges(expanded)
            for s, e in merged:
                lines.append(f"\n_(Zeilen {s}-{e} von {total})_")
                lines.append("```")
                lines.append("\n".join(f"{i:5d} | {file_lines[i-1]}" for i in range(s, e + 1)))
                lines.append("```")
        elif total > FALLBACK_TOC_THRESHOLD:
            # Kein Anker UND Datei zu groß für Blind-Load: Hinweis statt Code
            lines.append(
                f"\n_Datei zu groß ({total} Zeilen) und kein Issue-spezifischer Anker "
                f"gefunden — kein Code-Auszug geladen. Das Skeleton (siehe oben) zeigt "
                f"Signaturen mit Zeilennummern. Bei Bedarf konkret referenzieren "
                f"(z.B. `{rel}:L100-L150`)._"
            )
        else:
            head = min(total, max_lines)
            lines.append(f"\n_(Erste {head} Zeilen von {total} — kein spezifischer Anker gefunden)_")
            lines.append("```")
            lines.append("\n".join(f"{i:5d} | {file_lines[i-1]}" for i in range(1, head + 1)))
            lines.append("```")
    return "\n".join(lines)


def render_constraints_section(constraints: list[str]) -> str:
    if not constraints:
        return ""
    return "## Architektur-Constraints\n" + "\n".join(f"- {c}" for c in constraints)


def _path_matches_module(pattern: str, file_path: str) -> bool:
    if pattern.endswith("/"):
        return file_path.startswith(pattern)
    return file_path == pattern or file_path.startswith(pattern + "/")


def _resolve_module_info(files: list[str], modules: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen_paths: set[str] = set()
    for mod in modules:
        mod_path = mod.get("path", "")
        if not mod_path or mod_path in seen_paths:
            continue
        if any(_path_matches_module(mod_path, f) for f in files):
            result.append(mod)
            seen_paths.add(mod_path)
    return result


def _resolve_expansion_scope(
    files: list[str], modules: list[dict], policy: dict,
) -> dict[str, Any]:
    allowed: set[str] = set()
    blocked: set[str] = set()
    roles: set[str] = set()
    for f in files:
        for mod in modules:
            mod_path = mod.get("path", "")
            if mod_path and _path_matches_module(mod_path, f):
                roles.add(mod.get("role", ""))
    for role in roles:
        p = policy.get(role, {})
        allowed.update(p.get("allowed_scopes", []))
        blocked.update(p.get("blocked_scopes", []))
    return {"allowed": allowed, "blocked": blocked, "roles": roles}


def render_module_context_section(module_info: list[dict]) -> str:
    if not module_info:
        return ""
    lines = ["## Betroffene Module (Architektur-Rolle)"]
    for m in module_info:
        role = m.get("role", "")
        desc = m.get("description", "")
        constraints = m.get("constraints", [])
        lines.append(f"\n### {m['path']}  ({role})")
        if desc:
            lines.append(f"_{desc}_")
        for c in constraints:
            lines.append(f"- {c}")
    return "\n".join(lines)


def build_full_context(
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
) -> dict[str, str]:
    keywords = extract_keywords(issue_title, issue_body, plan_text)
    plan_files = extract_plan_files(f"{issue_body}\n{plan_text}", project_root)

    # Architecture: ermittle erlaubte/blockierte Scopes BASIEREND auf den initialen plan_files
    arch_scope: dict[str, Any] = {}
    module_info: list[dict] = []
    global_constraints: list[str] = list(architecture_constraints or [])
    arch_path = architecture_config_path or (project_root / "config" / "architecture.json")
    arch_data: dict[str, Any] = {}
    if arch_path.exists():
        try:
            import json as _json
            arch_data = _json.loads(arch_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            arch_data = {}

    if arch_data:
        if not global_constraints:
            global_constraints = list(arch_data.get("global_constraints", []))
        module_info = _resolve_module_info(plan_files, arch_data.get("modules", []))
        arch_scope = _resolve_expansion_scope(
            plan_files, arch_data.get("modules", []), arch_data.get("expansion_policy", {}),
        )

    if skeleton_builders:
        plan_files = expand_via_symbol_references(
            plan_files, project_root,
            builders=skeleton_builders,
            exclude_dirs=exclude_dirs,
            allowed_scopes=arch_scope.get("allowed") or None,
            blocked_scopes=arch_scope.get("blocked") or None,
        )
    issue_text_for_matching = f"{issue_title}\n{issue_body}\n{plan_text}"

    skeleton_matches: list[tuple[str, SkeletonEntry]] = []
    if skeleton_builders:
        skeleton_matches = filter_skeleton(
            skeleton_builders, project_root,
            issue_text=issue_text_for_matching,
            plan_files=plan_files,
            exclude_dirs=exclude_dirs,
        )

    grep_hits = grep_keywords(
        project_root, keywords[:5],
        extensions=keyword_extensions, exclude_dirs=exclude_dirs,
        allowed_scopes=arch_scope.get("allowed") or None,
        blocked_scopes=arch_scope.get("blocked") or None,
    )

    return {
        "keywords": ", ".join(keywords),
        "plan_files": "\n".join(f"- `{f}`" for f in plan_files) if plan_files else "",
        "skeleton": render_skeleton_section(skeleton_matches),
        "grep": render_grep_section(grep_hits),
        "relevant_files": render_files_section(
            project_root, plan_files,
            skeleton_matches=skeleton_matches,
            grep_hits=grep_hits,
        ),
        "module_context": render_module_context_section(module_info),
        "constraints": render_constraints_section(global_constraints),
    }
