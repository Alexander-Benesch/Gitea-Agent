from __future__ import annotations

from samuel.adapters.skeleton.config_builder import StructuredConfigBuilder
from samuel.adapters.skeleton.python_ast import PythonASTBuilder
from samuel.adapters.skeleton.sql_builder import SQLBuilder
from samuel.adapters.skeleton.tree_sitter_go import GoRegexBuilder
from samuel.adapters.skeleton.tree_sitter_ts import TreeSitterTSBuilder
from samuel.core.ports import ISkeletonBuilder

_ts_builder = TreeSitterTSBuilder()
_config_builder = StructuredConfigBuilder()

SKELETON_BUILDERS: dict[str, ISkeletonBuilder] = {
    ".py": PythonASTBuilder(),
    ".ts": _ts_builder,
    ".tsx": _ts_builder,
    ".js": _ts_builder,
    ".jsx": _ts_builder,
    ".go": GoRegexBuilder(),
    ".sql": SQLBuilder(),
    ".json": _config_builder,
    ".yaml": _config_builder,
    ".yml": _config_builder,
    ".toml": _config_builder,
}
