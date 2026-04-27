from __future__ import annotations

import logging
import os
from pathlib import Path

from samuel.core.bus import (
    AuditMiddleware,
    Bus,
    ErrorMiddleware,
    IdempotencyMiddleware,
    IdempotencyStore,
    MetricsMiddleware,
    PromptGuardMiddleware,
    SecurityMiddleware,
)
from samuel.core.config import FileConfig, load_scm_config
from samuel.core.logging import setup_logging

log = logging.getLogger(__name__)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


def bootstrap(config_path: str | Path = "config") -> Bus:
    # Step 0: .env laden (überschreibt keine bestehenden Env-Vars)
    _load_dotenv(Path(".env"))

    # Step 1: Config laden + Pydantic-Validierung
    config = FileConfig(config_path)

    # Step 2: Logging
    log_level = config.get("agent.log_level", "INFO")
    log_file = config.get("agent.log_file")
    max_log_mb = int(config.get("agent.logging.max_log_size_mb", 10))
    setup_logging(level=str(log_level), log_file=log_file, max_log_size_mb=max_log_mb)

    # Step 3: Bus + Middleware-Kette aufbauen
    bus = Bus()

    store_path = Path(config.get("agent.data_dir", "data")) / "idempotency.json"
    bus.add_middleware(IdempotencyMiddleware(IdempotencyStore(path=store_path)))
    bus.add_middleware(SecurityMiddleware())
    bus.add_middleware(PromptGuardMiddleware())
    bus.add_middleware(AuditMiddleware())
    bus.add_middleware(ErrorMiddleware(bus=bus))
    bus.add_middleware(MetricsMiddleware())

    # Step 4: Audit-Sinks verdrahten (muss vor Health-Check stehen)
    audit_sink = None
    try:
        from samuel.adapters.audit.async_sink import AsyncAuditSink
        from samuel.adapters.audit.jsonl import JSONLAuditSink
        from samuel.core.config import load_audit_config

        audit_config = load_audit_config(config_path)
        for sink_cfg in audit_config.sinks:
            if sink_cfg.type == "jsonl":
                path = sink_cfg.path or "data/logs/agent.jsonl"
                inner = JSONLAuditSink(path=path, rotation=sink_cfg.rotation or "daily")
                fallback = JSONLAuditSink(path=f"{path}.fallback", rotation="none")
                audit_sink = AsyncAuditSink(inner=inner, fallback=fallback)
                break
        if audit_sink:
            for mw in bus._middlewares:
                if isinstance(mw, AuditMiddleware):
                    mw._sink = audit_sink
                    break
            log.info("Audit: sink configured (%s)", audit_config.sinks[0].type if audit_config.sinks else "none")
    except Exception as exc:
        log.warning("Audit sinks not configured: %s", exc)

    # Step 5: SCM-Adapter + Auth
    try:
        scm_config = load_scm_config()
        from samuel.adapters.auth.static_token import StaticTokenAuth
        from samuel.adapters.gitea.adapter import GiteaAdapter

        auth = StaticTokenAuth(scm_config.token)
        scm = GiteaAdapter(scm_config.url, scm_config.repo, auth)
        log.info("SCM: %s adapter for %s", scm_config.provider, scm_config.repo)
    except ValueError:
        scm = None
        log.warning("SCM not configured, running without version control")
    # Step 6: LLM-Adapter + Circuit Breaker
    llm = None
    try:
        from samuel.adapters.llm.factory import create_llm_adapter
        from samuel.adapters.secrets.env_secrets import EnvSecretsProvider

        llm = create_llm_adapter(config, EnvSecretsProvider())
        log.info("LLM: adapter created (provider=%s)", config.get("llm.default.provider", "ollama"))
    except Exception as exc:
        log.warning("LLM not configured: %s", exc)
    # Step 7: Optional Premium Modules
    try:
        from samuel.premium.llm_routing.handler import create_routing_provider

        if llm and config.get("premium.llm_routing.enabled", False):
            providers = {"default": llm}
            llm = create_routing_provider(providers, config=config)
            log.info("Premium: LLM routing enabled")
    except ImportError:
        pass  # Premium modules not installed

    try:
        from samuel.premium.token_limit.handler import TokenLimitHandler

        if config.get("premium.token_limit.enabled", False):
            token_limit = TokenLimitHandler(bus, config=config)
            bus._token_limit = token_limit  # type: ignore[attr-defined]
            log.info("Premium: Token limit enabled")
    except ImportError:
        pass  # Premium modules not installed

    # Step 8: Slices registrieren
    from samuel.slices.planning.handler import PlanningHandler

    planning = PlanningHandler(bus, scm=scm, llm=llm)
    bus.register_command("PlanIssue", planning.handle)

    from samuel.adapters.skeleton.registry import SKELETON_BUILDERS as _SK
    from samuel.slices.architecture.handler import ArchitectureHandler
    from samuel.slices.implementation.handler import ImplementationHandler

    _arch = ArchitectureHandler(bus, project_root=Path("."))
    _exclude_dirs = set(config.get("agent.context.exclude_dirs", []) or [])
    _kw_ext = set(config.get("agent.context.keyword_extensions", []) or [])
    implementation = ImplementationHandler(
        bus, scm=scm, llm=llm,
        project_root=Path("."),
        skeleton_builders=list(_SK.values()),
        architecture_constraints=_arch.get_constraints(),
        exclude_dirs=_exclude_dirs or None,
        keyword_extensions=_kw_ext or None,
    )
    bus.register_command("Implement", implementation.handle)

    from samuel.slices.pr_gates.handler import PRGatesHandler
    from samuel.slices.privacy.ai_act import ai_attribution_trailer

    pr_gates = PRGatesHandler(
        bus, scm=scm,
        config_dir=str(config.get("agent.config_dir", config_path)),
        ai_attribution_fn=lambda: ai_attribution_trailer("S.A.M.U.E.L.", "v2"),
    )
    bus.register_command("CreatePR", pr_gates.handle)

    from samuel.slices.evaluation.handler import EvaluationHandler

    evaluation = EvaluationHandler(
        bus, scm=scm,
        config_dir=str(config.get("agent.config_dir", config_path)),
        data_dir=str(config.get("agent.data_dir", "data")),
        config=config,
    )
    bus.register_command("Evaluate", evaluation.handle)

    from samuel.slices.watch.handler import WatchHandler

    watch = WatchHandler(bus, scm=scm, config=config, max_parallel=int(config.get("agent.max_parallel", 1)))
    bus.register_command("ScanIssues", watch.handle)

    from samuel.slices.healing.handler import HealingHandler

    healing = HealingHandler(bus, llm=llm, config=config)
    bus.register_command("Heal", healing.handle)

    from samuel.slices.health.handler import HealthHandler

    health = HealthHandler(bus, scm=scm, llm=llm, config=config)
    bus.register_command("HealthCheck", health.handle)

    from samuel.adapters.quality.registry import load_registry_from_config
    from samuel.slices.quality.handler import QualityHandler

    hooks_path = Path(str(config.get("agent.config_dir", config_path))) / "hooks.json"
    load_registry_from_config(hooks_path if hooks_path.exists() else None)

    quality = QualityHandler(bus)
    bus.register_command("RunQuality", quality.handle)

    from samuel.slices.ac_verification.handler import ACVerificationHandler

    ac_verify = ACVerificationHandler(bus)
    bus.register_command("VerifyAC", ac_verify.handle)

    from samuel.adapters.skeleton.registry import SKELETON_BUILDERS
    from samuel.slices.context.handler import ContextHandler

    _skeleton_builders = list(SKELETON_BUILDERS.values())

    context = ContextHandler(bus, config=config, skeleton_builders=_skeleton_builders)
    bus.register_command("BuildContext", context.handle)

    from samuel.slices.review.handler import ReviewHandler

    review = ReviewHandler(bus, scm=scm, llm=llm)
    bus.register_command("Review", review.handle)

    from samuel.slices.changelog.handler import ChangelogHandler

    changelog = ChangelogHandler(bus, scm=scm)
    bus.register_command("Changelog", changelog.handle)

    from samuel.slices.privacy.handler import PrivacyHandler

    privacy = PrivacyHandler(bus, config=config)
    bus.register_command("CheckRetention", lambda cmd: privacy.check_retention())

    from samuel.slices.security.handler import SecurityHandler

    SecurityHandler(bus, config=config)

    from samuel.slices.setup.handler import SetupHandler

    setup = SetupHandler(bus, config=config)
    setup.ensure_directories()

    from samuel.slices.labels.handler import LabelsHandler

    labels = LabelsHandler(bus, scm=scm)
    labels.register()
    bus.labels = labels

    from samuel.slices.session.handler import SessionHandler

    session = SessionHandler(bus, config=config)
    bus.session = session

    from samuel.slices.sequence.handler import SequenceHandler

    sequence = SequenceHandler(
        bus,
        mode=config.get("agent.sequence_validator", "warn"),
        patterns_path=Path(str(config.get("agent.config_dir", config_path))) / "repo_patterns.json",
    )
    bus.subscribe("*", lambda ev, _seq=sequence: _seq.record_event(ev.name))
    bus.sequence = sequence

    # Step 9: Startup-Validation (Health-Check)
    from samuel.core.commands import HealthCheckCommand

    health_result = bus.send(HealthCheckCommand(payload={}))
    if health_result:
        if not health_result.get("critical", True):
            log.error("Critical health checks failed: %s", health_result.get("checks"))
        else:
            log.info("Health: critical=%s, healthy=%s", health_result.get("critical"), health_result.get("healthy"))

    # Step 10: Workflow-Engine laden
    import os as _os
    mode = _os.environ.get("SAMUEL_WORKFLOW_OVERRIDE") or str(config.get("agent.mode", "standard"))
    workflow_file = Path(str(config.get("agent.config_dir", config_path))) / "workflows" / f"{mode}.json"
    if workflow_file.exists():
        import json as _json

        from samuel.core.workflow import WorkflowEngine

        with open(workflow_file) as f:
            wf_def = _json.load(f)
        WorkflowEngine(bus, wf_def)
        log.info("Workflow '%s' geladen (%d steps)", mode, len(wf_def.get("steps", [])))
    else:
        log.warning("Workflow-Definition '%s' nicht gefunden: %s", mode, workflow_file)

    # Step 11: Notification-Sinks laden
    try:
        notifications_path = Path(str(config.get("agent.config_dir", config_path))) / "notifications.json"
        if notifications_path.exists():
            import json as _json
            with open(notifications_path) as f:
                notif_data = _json.load(f)
            for adapter_cfg in notif_data.get("adapters", []):
                if not adapter_cfg.get("enabled", False):
                    continue
                atype = adapter_cfg.get("type", "")
                if atype == "slack":
                    from samuel.adapters.notifications.slack import SlackNotifier
                    sink = SlackNotifier(webhook_url=adapter_cfg["webhook_url"], channel=adapter_cfg.get("channel"))
                    bus.subscribe("*", lambda ev, _s=sink: _s.notify(ev))
                    log.info("Notification sink: Slack")
                elif atype == "teams":
                    from samuel.adapters.notifications.teams import TeamsNotifier
                    sink = TeamsNotifier(webhook_url=adapter_cfg["webhook_url"])
                    bus.subscribe("*", lambda ev, _s=sink: _s.notify(ev))
                    log.info("Notification sink: Teams")
                elif atype == "generic_webhook":
                    from samuel.adapters.notifications.generic_webhook import GenericWebhookNotifier
                    sink = GenericWebhookNotifier(url=adapter_cfg["url"], headers=adapter_cfg.get("headers", {}))
                    bus.subscribe("*", lambda ev, _s=sink: _s.notify(ev))
                    log.info("Notification sink: generic webhook")
    except Exception as exc:
        log.warning("Notification sinks not loaded: %s", exc)

    # Step 12: Signal-Handler + Graceful Shutdown werden in cli.py registriert

    bus.audit_sink = audit_sink
    bus.scm = scm
    bus.config = config
    return bus
