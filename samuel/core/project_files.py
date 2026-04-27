"""Sprachunabhängige zentrale Datei-Iteration für alle Slices.

Ersetzt verstreute rglob()-Aufrufe. Garantiert konsistente Exclude-Regeln
(venv, .git, node_modules, etc.), File-Size-Filter und optionale
Extension-Filter. Kein Slice scannt das Projekt mehr direkt.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".direnv", ".eggs", ".ruff_cache", "coverage", ".coverage",
    "htmlcov", ".hypothesis", ".nox", ".cache", "data",
    "target", "out", "bin", "obj",
})

DEFAULT_EXCLUDE_FILES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "uv.lock", "Cargo.lock",
    "go.sum", "composer.lock", "Gemfile.lock",
})

CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx",
    ".go",
    ".java", ".kt", ".scala", ".groovy",
    ".rs",
    ".rb",
    ".php",
    ".swift", ".m", ".mm",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
    ".cs", ".vb", ".fs",
    ".lua", ".ex", ".exs", ".erl", ".hrl",
    ".sh", ".bash", ".zsh",
    ".sql", ".lisp", ".clj", ".cljs", ".cljc",
})

CONFIG_EXTENSIONS: frozenset[str] = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".env",
})

DOC_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".rst", ".txt", ".adoc",
})


def iter_project_files(
    root: Path | str,
    *,
    extensions: Iterable[str] | None = None,
    max_size_kb: int | None = None,
    exclude_dirs: Iterable[str] | None = None,
    exclude_files: Iterable[str] | None = None,
    follow_symlinks: bool = False,
) -> Iterator[Path]:
    """Iteriere Projekt-Dateien mit konsistenter Exclude-Logik.

    Args:
        root: Projekt-Wurzel (absolut oder relativ).
        extensions: Nur Dateien mit diesen Suffixes (inkl. Dot, z.B. ".py").
                    None = alle Extensions.
        max_size_kb: Dateien über dieser Größe überspringen. None = keine Grenze.
        exclude_dirs: Zusätzliche Verzeichnis-Namen (merged mit DEFAULT_EXCLUDE_DIRS).
        exclude_files: Zusätzliche Datei-Namen (merged mit DEFAULT_EXCLUDE_FILES).
        follow_symlinks: Standard False (sicher gegen Zyklen).

    Yields:
        Path-Objekte relativ zum root.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        return

    excl_dirs = DEFAULT_EXCLUDE_DIRS | frozenset(exclude_dirs or ())
    excl_files = DEFAULT_EXCLUDE_FILES | frozenset(exclude_files or ())
    ext_filter = frozenset(extensions) if extensions is not None else None
    max_bytes = max_size_kb * 1024 if max_size_kb else None

    def _walk(dir_path: Path) -> Iterator[Path]:
        try:
            entries = list(dir_path.iterdir())
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.is_symlink() and not follow_symlinks:
                continue
            if entry.is_dir():
                if entry.name in excl_dirs:
                    continue
                yield from _walk(entry)
            elif entry.is_file():
                if entry.name in excl_files:
                    continue
                if ext_filter is not None and entry.suffix not in ext_filter:
                    continue
                if max_bytes is not None:
                    try:
                        if entry.stat().st_size > max_bytes:
                            continue
                    except OSError:
                        continue
                yield entry

    yield from _walk(root_path)


def list_project_files(
    root: Path | str,
    **kwargs,
) -> list[Path]:
    """Convenience: iter_project_files als sortierte Liste."""
    return sorted(iter_project_files(root, **kwargs))
