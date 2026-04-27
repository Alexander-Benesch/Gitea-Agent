from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _load_env_file(path: Path, *, override: bool) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def _activate_self_mode(project_root: Path) -> Path | None:
    base_env = project_root / ".env"
    agent_env = project_root / ".env.agent"
    _load_env_file(base_env, override=False)
    if agent_env.exists():
        _load_env_file(agent_env, override=True)
        os.environ["SAMUEL_SELF_MODE"] = "1"
        os.environ["SAMUEL_ENV_FILE"] = str(agent_env)
        return agent_env
    os.environ["SAMUEL_SELF_MODE"] = "1"
    return None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="samuel",
        description="S.A.M.U.E.L. — Sicheres Autonomes Mehrschichtiges "
        "Ueberwachungs- und Entwicklungs-Logiksystem",
    )
    p.add_argument(
        "--config", default="config", help="Pfad zum config-Verzeichnis (default: config)",
    )
    p.add_argument(
        "--log-level", default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log-Level (ueberschreibt config/agent.json)",
    )
    p.add_argument(
        "--self", dest="self_mode", action="store_true",
        help="Self-Mode: Agent arbeitet am eigenen Repo (lädt .env.agent-Override)",
    )

    sub = p.add_subparsers(dest="command")

    # --- watch: Polling-Loop ---
    w = sub.add_parser("watch", help="Polling-Modus: Issues scannen und abarbeiten")
    w.add_argument("--interval", type=int, default=60, help="Poll-Intervall in Sekunden")
    w.add_argument("--once", action="store_true", help="Einmal scannen, dann beenden")

    # --- run: Einzelnes Issue bearbeiten ---
    r = sub.add_parser("run", help="Einzelnes Issue durch Workflow schicken")
    r.add_argument("issue", type=int, help="Issue-Nummer")
    r.add_argument("--workflow", default="standard", help="Workflow-Name (default: standard)")

    # --- health: Health-Check ---
    sub.add_parser("health", help="Health-Check ausfuehren und Ergebnis ausgeben")

    # --- dashboard: HTTP-Server + Dashboard ---
    d = sub.add_parser("dashboard", help="HTTP-Server mit Dashboard + REST-API starten")
    d.add_argument("--host", default="0.0.0.0", help="Bind-Adresse (default: 0.0.0.0)")
    d.add_argument("--port", type=int, default=7777, help="Port (default: 7777)")

    # --- setup-labels: Gitea-Labels gemäß config/labels.json anlegen ---
    sub.add_parser("setup-labels", help="Workflow-/Risk-/Scope-Labels auf SCM anlegen (idempotent)")

    return p


def _cmd_watch(bus, args) -> int:
    import time

    from samuel.core.commands import ScanIssuesCommand

    cfg = getattr(bus, "config", None)
    interval = args.interval
    poll_timeout = 0
    if cfg:
        interval = int(cfg.get("agent.auto.poll_interval", interval))
        poll_timeout = int(cfg.get("agent.auto.poll_timeout", 0))
    # CLI flag overrides config when explicitly provided
    if args.interval != 60:  # 60 is the argparse default
        interval = args.interval

    log.info("Watch-Modus gestartet (interval=%ds, timeout=%ds, once=%s)", interval, poll_timeout, args.once)
    elapsed = 0
    while True:
        try:
            cmd = ScanIssuesCommand(payload={})
            result = bus.send(cmd)
            log.info("Scan abgeschlossen: %s", result)
        except Exception:
            log.exception("Fehler im Watch-Loop")
        if args.once:
            break
        if poll_timeout and elapsed >= poll_timeout:
            log.info("Poll-Timeout (%ds) erreicht, beende Watch-Loop", poll_timeout)
            break
        time.sleep(interval)
        elapsed += interval
    return 0


def _cmd_run(bus, args) -> int:
    from samuel.core.events import Event

    event = Event(name="IssueReady", payload={"issue_number": args.issue})
    bus.publish(event)
    return 0


def _cmd_health(bus, _args) -> int:
    from samuel.core.commands import HealthCheckCommand

    cmd = HealthCheckCommand(payload={})
    result = bus.send(cmd)
    if result:
        healthy = result.get("healthy", False)
        print(f"Health: {'healthy' if healthy else 'unhealthy'}")
        for k, v in result.items():
            if k != "healthy":
                print(f"  {k}: {v}")
        return 0 if healthy else 1
    print("Health: no response")
    return 1


def _cmd_setup_labels(bus, args) -> int:
    from samuel.slices.setup.handler import SetupHandler

    scm = getattr(bus, "scm", None)
    if scm is None:
        print("SCM adapter not available — check SCM_URL/SCM_TOKEN/SCM_REPO")
        return 1

    handler = SetupHandler(bus, project_root=Path(args.config).parent.resolve(), scm=scm)
    result = handler.sync_labels(Path(args.config) / "labels.json")

    total = result.get("total", 0)
    created = result.get("created", [])
    skipped = result.get("skipped", [])
    errors = result.get("errors", [])

    print(f"Labels sync: {len(created)} created, {len(skipped)} existing, {len(errors)} errors (of {total})")
    for name in created:
        print(f"  + {name}")
    for name in skipped:
        print(f"  = {name}")
    for err in errors:
        print(f"  ! {err}")

    if not result.get("synced"):
        err = result.get("error")
        if err:
            print(f"Error: {err}")
        return 1
    return 0


def _cmd_dashboard(bus, args) -> int:
    from samuel.server import create_server

    server = create_server(
        bus, host=args.host, port=args.port,
        scm=getattr(bus, "scm", None),
        config=getattr(bus, "config", None),
    )
    log.info("Dashboard: http://%s:%d/", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.self_mode:
        project_root = Path(args.config).resolve().parent
        agent_env = _activate_self_mode(project_root)
        log.info("Self-Mode aktiviert (root=%s, env_override=%s)", project_root, agent_env)

    if getattr(args, "workflow", None):
        os.environ["SAMUEL_WORKFLOW_OVERRIDE"] = args.workflow

    from samuel.core.bootstrap import bootstrap

    if args.log_level:
        logging.getLogger().setLevel(args.log_level)

    bus = bootstrap(config_path=args.config)
    if args.self_mode and getattr(bus, "config", None):
        bus.config._overrides["agent.mode"] = "self"
        bus.config._overrides["agent.self_mode"] = True
    log.info("S.A.M.U.E.L. gestartet (config=%s%s)", args.config, ", self-mode" if args.self_mode else "")

    shutdown = False

    def _signal_handler(signum, _frame):
        nonlocal shutdown
        sig_name = signal.Signals(signum).name
        log.info("Signal %s empfangen, fahre herunter...", sig_name)
        shutdown = True

    signal.signal(signal.SIGINT, _signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _signal_handler)

    if args.command == "watch":
        rc = _cmd_watch(bus, args)
    elif args.command == "run":
        rc = _cmd_run(bus, args)
    elif args.command == "health":
        rc = _cmd_health(bus, args)
    elif args.command == "dashboard":
        rc = _cmd_dashboard(bus, args)
    elif args.command == "setup-labels":
        rc = _cmd_setup_labels(bus, args)
    else:
        parser.print_help()
        rc = 0

    sys.exit(rc)
