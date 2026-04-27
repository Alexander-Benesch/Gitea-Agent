from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


@dataclass
class Event:
    name: str
    payload: dict = field(default_factory=dict)
    ts: datetime = field(default_factory=_now)
    source: str = ""
    event_version: int = 1
    correlation_id: str = field(default_factory=_uuid)
    causation_id: str | None = None


# --- Workflow Events ---


@dataclass
class IssueReady(Event):
    name: str = "IssueReady"


@dataclass
class PlanCreated(Event):
    name: str = "PlanCreated"


@dataclass
class PlanValidated(Event):
    name: str = "PlanValidated"


@dataclass
class PlanBlocked(Event):
    name: str = "PlanBlocked"


@dataclass
class PlanPosted(Event):
    name: str = "PlanPosted"


@dataclass
class PlanApproved(Event):
    name: str = "PlanApproved"


@dataclass
class PlanFeedbackReceived(Event):
    name: str = "PlanFeedbackReceived"


@dataclass
class PlanRetry(Event):
    name: str = "PlanRetry"


@dataclass
class PlanRevised(Event):
    name: str = "PlanRevised"


@dataclass
class CodeGenerated(Event):
    name: str = "CodeGenerated"


@dataclass
class QualityPassed(Event):
    name: str = "QualityPassed"


@dataclass
class QualityFailed(Event):
    name: str = "QualityFailed"


@dataclass
class PRCreated(Event):
    name: str = "PRCreated"


@dataclass
class GateFailedEvent(Event):
    name: str = "GateFailed"


@dataclass
class EvalCompleted(Event):
    name: str = "EvalCompleted"


@dataclass
class EvalFailed(Event):
    name: str = "EvalFailed"


# --- Terminal Events ---


@dataclass
class WorkflowBlocked(Event):
    name: str = "WorkflowBlocked"


@dataclass
class WorkflowAborted(Event):
    name: str = "WorkflowAborted"


@dataclass
class LLMUnavailable(Event):
    name: str = "LLMUnavailable"


# --- Framework Events ---


@dataclass
class TokenLimitHit(Event):
    name: str = "TokenLimitHit"


@dataclass
class ConfigReloaded(Event):
    name: str = "ConfigReloaded"


@dataclass
class CommandDeduplicated(Event):
    name: str = "CommandDeduplicated"


@dataclass
class UnhandledCommand(Event):
    name: str = "UnhandledCommand"


@dataclass
class AuditEvent(Event):
    name: str = "AuditEvent"


@dataclass
class SecurityTripwireTriggered(Event):
    name: str = "SecurityTripwireTriggered"


@dataclass
class PreCommitCheckCompleted(Event):
    name: str = "PreCommitCheckCompleted"


@dataclass
class StartupBlocked(Event):
    name: str = "StartupBlocked"


@dataclass
class ProviderCircuitOpen(Event):
    name: str = "ProviderCircuitOpen"


@dataclass
class CheckpointSaved(Event):
    name: str = "CheckpointSaved"


@dataclass
class LLMCallCompleted(Event):
    name: str = "LLMCallCompleted"


@dataclass
class HealingFailed(Event):
    name: str = "HealingFailed"


@dataclass
class ImplementationFailed(Event):
    name: str = "ImplementationFailed"


@dataclass
class ConfigValidationFailed(Event):
    name: str = "ConfigValidationFailed"


@dataclass
class ProviderFallbackUsed(Event):
    name: str = "ProviderFallbackUsed"


@dataclass
class BranchCreated(Event):
    name: str = "BranchCreated"


@dataclass
class BranchDeleted(Event):
    name: str = "BranchDeleted"


@dataclass
class SkeletonRebuilt(Event):
    name: str = "SkeletonRebuilt"


@dataclass
class QualityRetry(Event):
    name: str = "QualityRetry"


@dataclass
class IssueSkipped(Event):
    name: str = "IssueSkipped"


@dataclass
class HookIntegrityFailed(Event):
    name: str = "HookIntegrityFailed"
