from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


def _uuid() -> str:
    return str(uuid4())


@dataclass
class Command:
    name: str
    payload: dict = field(default_factory=dict)
    idempotency_key: str | None = None
    correlation_id: str | None = field(default_factory=_uuid)


@dataclass
class ScanIssuesCommand(Command):
    name: str = "ScanIssues"


@dataclass
class PlanIssueCommand(Command):
    name: str = "PlanIssue"
    issue_number: int = 0


@dataclass
class ImplementCommand(Command):
    name: str = "Implement"
    issue_number: int = 0


@dataclass
class CreatePRCommand(Command):
    name: str = "CreatePR"
    issue_number: int = 0
    branch: str = ""
    base: str = "main"


@dataclass
class EvaluateCommand(Command):
    name: str = "Evaluate"
    issue_number: int = 0


@dataclass
class HealCommand(Command):
    name: str = "Heal"


@dataclass
class ReviewCommand(Command):
    name: str = "Review"


@dataclass
class HealthCheckCommand(Command):
    name: str = "HealthCheck"


@dataclass
class ReloadConfigCommand(Command):
    name: str = "ReloadConfig"


@dataclass
class ShutdownCommand(Command):
    name: str = "Shutdown"


@dataclass
class BuildContextCommand(Command):
    name: str = "BuildContext"


@dataclass
class RunQualityCommand(Command):
    name: str = "RunQuality"


@dataclass
class VerifyACCommand(Command):
    name: str = "VerifyAC"


@dataclass
class ChangelogCommand(Command):
    name: str = "Changelog"


@dataclass
class CheckRetentionCommand(Command):
    name: str = "CheckRetention"


COMMAND_REGISTRY: dict[str, type[Command]] = {
    "ScanIssues": ScanIssuesCommand,
    "PlanIssue": PlanIssueCommand,
    "Implement": ImplementCommand,
    "CreatePR": CreatePRCommand,
    "Evaluate": EvaluateCommand,
    "Heal": HealCommand,
    "Review": ReviewCommand,
    "HealthCheck": HealthCheckCommand,
    "ReloadConfig": ReloadConfigCommand,
    "Shutdown": ShutdownCommand,
    "BuildContext": BuildContextCommand,
    "RunQuality": RunQualityCommand,
    "VerifyAC": VerifyACCommand,
    "Changelog": ChangelogCommand,
    "CheckRetention": CheckRetentionCommand,
}


_PAYLOAD_ALIASES = {"issue": "issue_number"}


def create_command(name: str, payload: dict | None = None, **kwargs) -> Command:
    cls = COMMAND_REGISTRY.get(name, Command)
    p = payload or {}
    init_fields = {f.name for f in cls.__dataclass_fields__.values()} - {"name", "payload", "idempotency_key", "correlation_id"}
    extra = {}
    for k in init_fields:
        if k in p:
            extra[k] = p[k]
        else:
            for alias, target in _PAYLOAD_ALIASES.items():
                if target == k and alias in p:
                    extra[k] = p[alias]
                    break
    return cls(payload=p, **extra, **kwargs)
