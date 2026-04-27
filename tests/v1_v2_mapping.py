"""v1 → v2 file mapping for migration completeness verification.

Each v1 source file maps to one or more v2 targets, or is marked as 'removed'
with a reason. The test_every_v1_file_mapped() architecture test uses this
mapping to verify no v1 functionality was lost during migration.
"""
from __future__ import annotations

# v1 root: /home/ki02/gitea-agent/
# v2 root: /home/ki02/samuel/samuel/
#
# Format: "v1_path" -> [("v2_path_relative_to_samuel/", "note")]
# Special target "removed" means functionality was intentionally dropped or absorbed.

V1_V2_MAPPING: dict[str, list[tuple[str, str]]] = {
    # === Root modules ===
    "agent_start.py": [
        ("cli.py", "CLI entry point, argparse + bootstrap"),
    ],
    "agent_self_check.py": [
        ("slices/health/handler.py", "Self-check via HealthCheckCommand"),
    ],
    "code_analyzer.py": [
        ("slices/code_analysis/handler.py", "CVE + code-smell analysis"),
    ],
    "context_loader.py": [
        ("slices/context/handler.py", "Context loading + slice requests"),
        ("adapters/skeleton/python_ast.py", "AST-based skeleton builder"),
        ("adapters/skeleton/registry.py", "Skeleton builder registry"),
    ],
    "evaluation.py": [
        ("slices/evaluation/handler.py", "Evaluation workflow"),
        ("slices/evaluation/scoring.py", "Score pipeline + baselines"),
    ],
    "gitea_api.py": [
        ("adapters/gitea/adapter.py", "IVersionControl implementation"),
        ("adapters/gitea/api.py", "Low-level Gitea HTTP client"),
    ],
    "helpers.py": [
        ("core/types.py", "strip_html, safe_int, safe_float, validate_comment"),
        ("core/errors.py", "AgentAbort with event publishing"),
        ("core/config.py", "_get_project → IConfig"),
    ],
    "issue_helpers.py": [
        ("slices/planning/handler.py", "Issue parsing absorbed into planning"),
        ("slices/watch/handler.py", "Issue filtering absorbed into watch"),
    ],
    "session.py": [
        ("slices/session/handler.py", "Session limits + token budget"),
    ],
    "settings.py": [
        ("core/config.py", "IConfig port with Pydantic schemas"),
    ],
    "workspace.py": [
        ("removed", "Workspace isolation absorbed into bootstrap + slices"),
    ],
    # === commands/ ===
    "commands/__init__.py": [
        ("removed", "No command registry needed — Bus dispatches"),
    ],
    "commands/analyze.py": [
        ("slices/code_analysis/handler.py", "AnalyzeCommand handler"),
    ],
    "commands/auto.py": [
        ("core/workflow.py", "WorkflowEngine orchestration"),
        ("slices/watch/handler.py", "Auto-mode = watch + workflow"),
    ],
    "commands/chat_workflow.py": [
        ("slices/security/handler.py", "Chat workflow HMAC + lock"),
    ],
    "commands/check_deps.py": [
        ("slices/code_analysis/handler.py", "Dependency check absorbed"),
    ],
    "commands/complete.py": [
        ("removed", "Completion logic absorbed into planning slice"),
    ],
    "commands/dashboard_cmd.py": [
        ("slices/dashboard/handler.py", "Dashboard command"),
        ("server.py", "HTTP server for dashboard"),
    ],
    "commands/doctor.py": [
        ("slices/health/handler.py", "Doctor = HealthCheckCommand"),
    ],
    "commands/eval_after_restart.py": [
        ("slices/evaluation/handler.py", "Post-restart eval"),
    ],
    "commands/fixup.py": [
        ("slices/healing/handler.py", "Fixup = HealCommand"),
    ],
    "commands/generate_tests.py": [
        ("slices/architecture/handler.py", "Test generation"),
    ],
    "commands/get_llm_cmd.py": [
        ("adapters/llm/factory.py", "LLM provider selection via factory"),
    ],
    "commands/get_slice.py": [
        ("slices/context/handler.py", "Slice context requests"),
    ],
    "commands/heal.py": [
        ("slices/healing/handler.py", "HealCommand handler"),
    ],
    "commands/implement_llm.py": [
        ("slices/implementation/llm_loop.py", "LLM code generation loop"),
        ("slices/implementation/handler.py", "ImplementCommand handler"),
    ],
    "commands/implement.py": [
        ("slices/implementation/handler.py", "Implementation orchestration"),
    ],
    "commands/install_service.py": [
        ("slices/setup/handler.py", "Service installation"),
    ],
    "commands/list_cmd.py": [
        ("cli.py", "Thin CLI subcommand"),
    ],
    "commands/plan.py": [
        ("slices/planning/handler.py", "PlanIssueCommand handler"),
    ],
    "commands/pr.py": [
        ("slices/pr_gates/handler.py", "PRGatesHandler"),
        ("slices/pr_gates/gates.py", "Individual gate checks"),
    ],
    "commands/review.py": [
        ("slices/review/handler.py", "ReviewCommand handler"),
    ],
    "commands/setup.py": [
        ("slices/setup/handler.py", "Setup wizard"),
    ],
    "commands/watch.py": [
        ("slices/watch/handler.py", "WatchHandler with semaphore"),
    ],
    # === plugins/ ===
    "plugins/__init__.py": [
        ("removed", "Plugin registry replaced by Bus subscriptions"),
    ],
    "plugins/ac_verification.py": [
        ("slices/ac_verification/handler.py", "AC tag registry"),
    ],
    "plugins/architecture_context.py": [
        ("slices/architecture/handler.py", "Architecture constraints"),
    ],
    "plugins/architecture_test_gen.py": [
        ("slices/architecture/handler.py", "Test generation from constraints"),
    ],
    "plugins/audit.py": [
        ("slices/audit_trail/handler.py", "Audit event handler"),
        ("slices/audit_trail/bridge.py", "Legacy audit bridge"),
        ("adapters/audit/jsonl.py", "JSONL audit sink"),
        ("adapters/audit/upcasters.py", "Event schema upcasters"),
    ],
    "plugins/changelog.py": [
        ("slices/changelog/handler.py", "ChangelogCommand handler"),
    ],
    "plugins/context_compactor.py": [
        ("slices/context/handler.py", "Context compaction absorbed"),
    ],
    "plugins/dep_checker.py": [
        ("slices/code_analysis/handler.py", "Dependency checking"),
    ],
    "plugins/docstring_check.py": [
        ("slices/code_analysis/handler.py", "Docstring analysis absorbed"),
    ],
    "plugins/healing.py": [
        ("slices/healing/handler.py", "Healing logic"),
        ("slices/healing/events.py", "Healing events"),
    ],
    "plugins/health.py": [
        ("slices/health/handler.py", "Health checks"),
    ],
    "plugins/llm_config_guard.py": [
        ("core/config.py", "LLM config validation via Pydantic schemas"),
    ],
    "plugins/llm_costs.py": [
        ("adapters/llm/costs.py", "LLM cost calculation"),
    ],
    "plugins/llm_mock.py": [
        ("removed", "Test mocks live in test fixtures, not production code"),
    ],
    "plugins/llm.py": [
        ("adapters/llm/claude.py", "Claude adapter"),
        ("adapters/llm/factory.py", "Provider factory + selection"),
    ],
    "plugins/llm_quality.py": [
        ("slices/quality/handler.py", "LLM output quality checks"),
    ],
    "plugins/llm_wizard.py": [
        ("slices/setup/handler.py", "LLM setup wizard absorbed into setup"),
    ],
    "plugins/log_anomaly.py": [
        ("slices/audit_trail/handler.py", "Log anomaly detection via audit"),
    ],
    "plugins/log.py": [
        ("core/logging.py", "Centralized logging setup"),
    ],
    "plugins/optimizer.py": [
        ("removed", "Optimizer absorbed into evaluation scoring"),
    ],
    "plugins/patch.py": [
        ("slices/implementation/patch_parser.py", "Patch parsing + application"),
    ],
    "plugins/pattern_miner.py": [
        ("slices/sequence/handler.py", "Bigram pattern mining"),
    ],
    "plugins/pr_validator.py": [
        ("slices/pr_gates/gates.py", "PR validation gates"),
    ],
    "plugins/quality_pipeline.py": [
        ("slices/quality/handler.py", "Quality pipeline orchestration"),
    ],
    "plugins/restart_manager.py": [
        ("slices/session/handler.py", "Restart + checkpoint management"),
    ],
    "plugins/resume.py": [
        ("slices/session/handler.py", "Resume from checkpoint"),
    ],
    "plugins/sequence_extractor.py": [
        ("slices/sequence/handler.py", "Sequence extraction"),
    ],
    "plugins/sequence_validator.py": [
        ("slices/sequence/handler.py", "Sequence validation"),
    ],
    "plugins/setup_wizard.py": [
        ("slices/setup/handler.py", "Interactive setup"),
    ],
    "plugins/slice_matching.py": [
        ("slices/context/handler.py", "Slice matching for context"),
    ],
    "plugins/tree_sitter_parser.py": [
        ("adapters/skeleton/python_ast.py", "AST parsing (tree-sitter planned for Phase 10)"),
    ],
    # === dashboard/ ===
    "dashboard/__init__.py": [
        ("slices/dashboard/handler.py", "Dashboard slice"),
        ("server.py", "HTTP server"),
    ],
    "dashboard/data.py": [
        ("slices/dashboard/handler.py", "Dashboard data aggregation"),
    ],
    # === config/ ===
    "config/log_analyzer.py": [
        ("removed", "Log analysis config absorbed into audit config"),
    ],
}
