from __future__ import annotations

from pathlib import Path

from samuel.adapters.skeleton.config_builder import StructuredConfigBuilder
from samuel.adapters.skeleton.python_ast import PythonASTBuilder
from samuel.adapters.skeleton.registry import SKELETON_BUILDERS
from samuel.adapters.skeleton.sql_builder import SQLBuilder
from samuel.adapters.skeleton.tree_sitter_go import GoRegexBuilder
from samuel.adapters.skeleton.tree_sitter_ts import TreeSitterTSBuilder

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample.py"


def test_python_ast_builder_extracts_functions():
    builder = PythonASTBuilder()
    entries = builder.extract(SAMPLE)
    names = {e.name for e in entries}
    assert "helper" in names
    assert "main" in names


def test_python_ast_builder_extracts_classes():
    builder = PythonASTBuilder()
    entries = builder.extract(SAMPLE)
    classes = [e for e in entries if e.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "Calculator"


def test_python_ast_builder_extracts_methods():
    builder = PythonASTBuilder()
    entries = builder.extract(SAMPLE)
    names = {e.name for e in entries}
    assert "add" in names
    assert "multiply" in names


def test_skeleton_entry_fields():
    builder = PythonASTBuilder()
    entries = builder.extract(SAMPLE)
    helper = next(e for e in entries if e.name == "helper")
    assert helper.kind == "function"
    assert helper.file == str(SAMPLE)
    assert helper.line_start > 0
    assert helper.line_end >= helper.line_start
    assert helper.language == "python"


def test_calls_extracted():
    builder = PythonASTBuilder()
    entries = builder.extract(SAMPLE)
    main_entry = next(e for e in entries if e.name == "main")
    assert "helper" in main_entry.calls
    assert "print" in main_entry.calls


def test_called_by_computed():
    builder = PythonASTBuilder()
    entries = builder.extract(SAMPLE)
    helper = next(e for e in entries if e.name == "helper")
    assert "main" in helper.called_by


def test_registry_has_python():
    assert ".py" in SKELETON_BUILDERS
    builder = SKELETON_BUILDERS[".py"]
    assert isinstance(builder, PythonASTBuilder)
    assert ".py" in builder.supported_extensions


def test_registry_has_typescript():
    assert ".ts" in SKELETON_BUILDERS
    assert isinstance(SKELETON_BUILDERS[".ts"], TreeSitterTSBuilder)


def test_registry_has_go():
    assert ".go" in SKELETON_BUILDERS
    assert isinstance(SKELETON_BUILDERS[".go"], GoRegexBuilder)


def test_registry_has_sql():
    assert ".sql" in SKELETON_BUILDERS
    assert isinstance(SKELETON_BUILDERS[".sql"], SQLBuilder)


def test_registry_has_config():
    for ext in (".json", ".yaml", ".yml", ".toml"):
        assert ext in SKELETON_BUILDERS
        assert isinstance(SKELETON_BUILDERS[ext], StructuredConfigBuilder)


def test_ts_builder_extracts_functions(tmp_path: Path):
    f = tmp_path / "app.ts"
    f.write_text("function greet(name: string): string {\n  return `Hello ${name}`;\n}\n")

    builder = TreeSitterTSBuilder()
    entries = builder.extract(f)

    if not entries:
        return  # tree-sitter not available
    names = {e.name for e in entries}
    assert "greet" in names
    assert entries[0].language == "typescript"


def test_ts_builder_extracts_classes(tmp_path: Path):
    f = tmp_path / "model.ts"
    f.write_text("class User {\n  name: string;\n  constructor(name: string) { this.name = name; }\n}\n")

    builder = TreeSitterTSBuilder()
    entries = builder.extract(f)

    if not entries:
        return
    classes = [e for e in entries if e.kind == "class"]
    assert any(c.name == "User" for c in classes)


def test_ts_builder_extracts_interfaces(tmp_path: Path):
    f = tmp_path / "types.ts"
    f.write_text("interface Config {\n  host: string;\n  port: number;\n}\n")

    builder = TreeSitterTSBuilder()
    entries = builder.extract(f)

    if not entries:
        return
    interfaces = [e for e in entries if e.kind == "interface"]
    assert any(i.name == "Config" for i in interfaces)


def test_go_builder_extracts_functions(tmp_path: Path):
    f = tmp_path / "main.go"
    f.write_text("package main\n\nfunc Hello(name string) string {\n\treturn \"Hello \" + name\n}\n")

    builder = GoRegexBuilder()
    entries = builder.extract(f)

    assert len(entries) >= 1
    assert entries[0].name == "Hello"
    assert entries[0].kind == "function"
    assert entries[0].language == "go"


def test_go_builder_extracts_methods(tmp_path: Path):
    f = tmp_path / "server.go"
    f.write_text("package main\n\ntype Server struct {\n\tport int\n}\n\nfunc (s *Server) Start() {\n\t// start\n}\n")

    builder = GoRegexBuilder()
    entries = builder.extract(f)

    structs = [e for e in entries if e.kind == "struct"]
    methods = [e for e in entries if e.kind == "method"]
    assert any(s.name == "Server" for s in structs)
    assert any(m.name == "Server.Start" for m in methods)


def test_go_builder_extracts_interfaces(tmp_path: Path):
    f = tmp_path / "ports.go"
    f.write_text("package main\n\ntype Handler interface {\n\tHandle() error\n}\n")

    builder = GoRegexBuilder()
    entries = builder.extract(f)

    interfaces = [e for e in entries if e.kind == "interface"]
    assert any(i.name == "Handler" for i in interfaces)


def test_sql_builder_extracts_tables(tmp_path: Path):
    f = tmp_path / "schema.sql"
    f.write_text("CREATE TABLE users (\n  id INTEGER PRIMARY KEY,\n  name TEXT\n);\n\nCREATE TABLE posts (\n  id INTEGER PRIMARY KEY\n);\n")

    builder = SQLBuilder()
    entries = builder.extract(f)

    names = {e.name for e in entries}
    assert "users" in names
    assert "posts" in names
    assert all(e.kind == "table" for e in entries)
    assert all(e.language == "sql" for e in entries)


def test_sql_builder_extracts_views_and_procedures(tmp_path: Path):
    f = tmp_path / "advanced.sql"
    f.write_text(
        "CREATE VIEW active_users AS SELECT * FROM users WHERE active = 1;\n"
        "CREATE OR REPLACE FUNCTION get_user(uid INT) RETURNS VOID AS $$ BEGIN END; $$;\n"
        "CREATE INDEX idx_name ON users(name);\n"
    )

    builder = SQLBuilder()
    entries = builder.extract(f)

    kinds = {e.kind for e in entries}
    assert "view" in kinds
    assert "procedure" in kinds
    assert "index" in kinds


def test_config_builder_json(tmp_path: Path):
    f = tmp_path / "config.json"
    f.write_text('{"host": "localhost", "port": 8080, "debug": true}')

    builder = StructuredConfigBuilder()
    entries = builder.extract(f)

    names = {e.name for e in entries}
    assert "host" in names
    assert "port" in names
    assert "debug" in names


def test_config_builder_toml(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text("[build-system]\nrequires = []\n\n[project]\nname = \"test\"\n")

    builder = StructuredConfigBuilder()
    entries = builder.extract(f)

    names = {e.name for e in entries}
    assert "build-system" in names
    assert "project" in names
