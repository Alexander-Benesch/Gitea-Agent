from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from samuel.core.types import (
    PR,
    AuditQuery,
    Comment,
    GateContext,
    GateResult,
    Issue,
    LLMResponse,
    SkeletonEntry,
)


class IVersionControl(ABC):
    @abstractmethod
    def get_issue(self, number: int) -> Issue: ...

    @abstractmethod
    def get_comments(self, number: int) -> list[Comment]: ...

    @abstractmethod
    def post_comment(self, number: int, body: str) -> Comment: ...

    @abstractmethod
    def create_pr(self, head: str, base: str, title: str, body: str) -> PR: ...

    @abstractmethod
    def swap_label(self, number: int, remove: str, add: str) -> None: ...

    @abstractmethod
    def list_labels(self) -> list[dict]: ...

    @abstractmethod
    def create_label(self, name: str, color: str, description: str = "") -> dict: ...

    @abstractmethod
    def list_issues(self, labels: list[str]) -> list[Issue]: ...

    @abstractmethod
    def close_issue(self, number: int) -> None: ...

    @abstractmethod
    def merge_pr(self, pr_id: int) -> bool: ...

    @abstractmethod
    def issue_url(self, number: int) -> str: ...

    @abstractmethod
    def pr_url(self, pr_id: int) -> str: ...

    @abstractmethod
    def branch_url(self, branch: str) -> str: ...

    @property
    def capabilities(self) -> set[str]:
        return set()


class ILLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse: ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int: ...

    @property
    @abstractmethod
    def context_window(self) -> int: ...

    @property
    def capabilities(self) -> set[str]:
        return set()


class IAuthProvider(ABC):
    @abstractmethod
    def get_token(self) -> str: ...

    @abstractmethod
    def is_valid(self) -> bool: ...

    @abstractmethod
    def refresh(self) -> None: ...


class IAuditLog(ABC):
    @abstractmethod
    def log(self, event: Any) -> str: ...

    @abstractmethod
    def read(self, **filters: Any) -> list[Any]: ...

    @abstractmethod
    def start_run(self, mode: str) -> str: ...


class IConfig(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    def feature_flag(self, name: str) -> bool: ...


class IAuditSink(ABC):
    @abstractmethod
    def write(self, event: Any) -> None: ...

    @abstractmethod
    def query(self, query: AuditQuery) -> list[Any]: ...


class ISecretsProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> str: ...


class ISkeletonBuilder(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def extract(self, file: Path) -> list[SkeletonEntry]: ...


class IPatchApplier(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def apply(self, file: Path, patches: list[Any]) -> Any: ...

    @abstractmethod
    def validate(self, file: Path, content: str) -> bool: ...


class INotificationSink(ABC):
    @abstractmethod
    def notify(self, event: Any) -> None: ...


class IQualityCheck(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any: ...


class IExternalGate(ABC):
    name: str

    @abstractmethod
    def run(self, context: GateContext) -> GateResult: ...


class IExternalEventSink(ABC):
    @abstractmethod
    def on_event(self, event: Any) -> None: ...


class IExternalTrigger(ABC):
    @abstractmethod
    def register(self, bus: Any) -> None: ...


class IDashboardRenderer(ABC):
    @abstractmethod
    def render_page(self, page: str, data: dict[str, Any]) -> str: ...

    @abstractmethod
    def get_api_data(self, endpoint: str, **params: Any) -> dict[str, Any]: ...


class IProjectRegistry(ABC):
    @abstractmethod
    def list_projects(self) -> list[Any]: ...

    @abstractmethod
    def get_config(self, project_id: str) -> Any: ...
