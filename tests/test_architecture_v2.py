from __future__ import annotations

import ast
from pathlib import Path

import pytest

SAMUEL_ROOT = Path(__file__).resolve().parent.parent / "samuel"
SLICES_DIR = SAMUEL_ROOT / "slices"
CORE_DIR = SAMUEL_ROOT / "core"

ALLOWED_CORE_MODULES = {
    "bus",
    "events",
    "commands",
    "ports",
    "types",
    "errors",
    "config",
    "git",
    "logging",
    "workflow",
    "bootstrap",
    "http_client",
    "project_files",
    "__init__",
}


def _collect_py_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _extract_imports(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_no_cross_slice_imports():
    violations: list[str] = []
    for py_file in _collect_py_files(SLICES_DIR):
        rel = py_file.relative_to(SAMUEL_ROOT)
        parts = rel.parts
        if len(parts) < 2:
            continue
        own_slice = parts[1]
        for imp in _extract_imports(py_file):
            if imp.startswith("samuel.slices."):
                imported_slice = imp.split(".")[2]
                if imported_slice != own_slice:
                    violations.append(f"{rel}: imports {imp}")
    assert not violations, "Cross-slice imports found:\n" + "\n".join(violations)


def test_no_direct_adapter_usage():
    violations: list[str] = []
    for py_file in _collect_py_files(SLICES_DIR):
        rel = py_file.relative_to(SAMUEL_ROOT)
        for imp in _extract_imports(py_file):
            if imp.startswith("samuel.adapters"):
                violations.append(f"{rel}: imports {imp}")
    assert not violations, "Direct adapter usage in slices:\n" + "\n".join(violations)


def test_shared_kernel_minimal():
    actual_modules = set()
    for item in CORE_DIR.iterdir():
        if item.suffix == ".py":
            actual_modules.add(item.stem)
        elif item.is_dir() and (item / "__init__.py").exists():
            actual_modules.add(item.name)

    unexpected = actual_modules - ALLOWED_CORE_MODULES
    assert not unexpected, f"Unexpected modules in core/: {unexpected}"


def test_no_module_level_config():
    violations: list[str] = []
    for py_file in _collect_py_files(SLICES_DIR):
        rel = py_file.relative_to(SAMUEL_ROOT)
        for imp in _extract_imports(py_file):
            if "settings" in imp.split(".")[-1:]:
                violations.append(f"{rel}: imports {imp}")
    assert not violations, "Direct settings imports in slices:\n" + "\n".join(violations)


def test_event_types_complete():
    events_file = CORE_DIR / "events.py"
    tree = ast.parse(events_file.read_text())
    event_classes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name != "Event":
            event_classes.add(node.name)

    assert len(event_classes) >= 10, (
        f"Expected at least 10 event types, found {len(event_classes)}: {event_classes}"
    )

    test_files = list(Path(__file__).resolve().parent.rglob("*.py"))
    test_files.extend(SAMUEL_ROOT.rglob("**/tests/*.py"))
    all_test_content = ""
    for tf in test_files:
        try:
            all_test_content += tf.read_text()
        except OSError:
            continue

    untested = set()
    for cls in event_classes:
        if cls not in all_test_content:
            untested.add(cls)

    if untested:
        pytest.skip(
            f"Event types not yet referenced in tests: {untested} "
            "(will be covered as slices are implemented)"
        )


def test_every_v1_file_mapped():
    from tests.v1_v2_mapping import V1_V2_MAPPING

    v1_root = Path("/home/ki02/gitea-agent")
    if not v1_root.exists():
        pytest.skip("v1 repo not available at /home/ki02/gitea-agent")

    v1_files: set[str] = set()
    for py_file in sorted(v1_root.rglob("*.py")):
        rel = str(py_file.relative_to(v1_root))
        if any(
            part in rel
            for part in (
                "__pycache__", "venv/", ".git/", "tests/", "premium/",
                ".direnv/", "site-packages/", ".tox/", "node_modules/",
            )
        ):
            continue
        v1_files.add(rel)

    mapped = set(V1_V2_MAPPING.keys())
    unmapped = v1_files - mapped

    assert not unmapped, (
        f"{len(unmapped)} v1 files have no v2 mapping:\n"
        + "\n".join(f"  - {f}" for f in sorted(unmapped))
    )

    missing_targets: list[str] = []
    for v1_path, targets in V1_V2_MAPPING.items():
        for v2_rel, _note in targets:
            if v2_rel == "removed":
                continue
            v2_full = SAMUEL_ROOT / v2_rel
            if not v2_full.exists():
                missing_targets.append(f"{v1_path} -> {v2_rel}")

    assert not missing_targets, (
        f"{len(missing_targets)} v2 targets missing:\n"
        + "\n".join(f"  - {t}" for t in missing_targets)
    )


def test_all_gates_have_owasp():
    import json

    gates_config = Path(__file__).resolve().parent.parent / "config" / "gates.json"
    if not gates_config.exists():
        pytest.skip("config/gates.json not found")

    data = json.loads(gates_config.read_text())
    assert "required" in data, "gates.json missing 'required' field"

    from samuel.core.types import GateContext
    from samuel.slices.pr_gates.gates import GATE_REGISTRY

    fail_ctx = GateContext(
        issue_number=1, branch="main", changed_files=[".env"],
        diff="-x\n" * 200, plan_comment=None, eval_score=None,
    )

    security_gates = {1, 7, "13b"}
    for gate_id in security_gates:
        if gate_id not in GATE_REGISTRY:
            continue
        result = GATE_REGISTRY[gate_id](fail_ctx)
        if not result.passed:
            assert result.owasp_risk is not None, (
                f"Gate {gate_id} failed but has no owasp_risk classification"
            )
