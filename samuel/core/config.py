from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from samuel.core.ports import IConfig

log = logging.getLogger(__name__)


# --- Pydantic Schemas ---


class WorkflowStepSchema(BaseModel):
    on: str
    send: str
    condition: str | None = None


class WorkflowSchema(BaseModel):
    name: str
    steps: list[WorkflowStepSchema]
    max_risk: int = 3
    max_parallel: int = 1


class GateSchema(BaseModel):
    id: int | str
    name: str
    enabled: bool = True
    owasp_risk: str | None = None


class GatesSchema(BaseModel):
    gates: list[GateSchema] = []


class GatesConfigSchema(BaseModel):
    required: list[int | str] = [1, 2, 3, 7, 8, 9, 11]
    optional: list[int | str] = [4, 5, 6, 10, 12, "13a", "13b"]
    disabled: list[int | str] = []
    custom: list[dict[str, Any]] = []


class EvalCriterionSchema(BaseModel):
    name: str
    weight: float = 1.0
    threshold: float = 0.5


class EvalSchema(BaseModel):
    criteria: list[EvalCriterionSchema] = []
    min_score: float = 0.6
    weights: dict[str, float] = {
        "test_pass_rate": 0.3,
        "syntax_valid": 0.2,
        "hallucination_free": 0.3,
        "scope_compliant": 0.2,
    }
    baseline: float = 0.8
    fail_fast_on: list[str] = []

    def model_post_init(self, __context: Any) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"weights must sum to 1.0, got {total:.4f}")
        known = set(self.weights)
        bad = [n for n in self.fail_fast_on if n not in known]
        if bad:
            raise ValueError(f"fail_fast_on references unknown checks: {bad}")


class AuditSinkSchema(BaseModel):
    type: str
    path: str | None = None
    url: str | None = None
    auth: str | None = None
    host: str | None = None
    index: str | None = None
    rotation: str | None = None


class AuditSchema(BaseModel):
    sinks: list[AuditSinkSchema] = []

    @classmethod
    def default(cls) -> AuditSchema:
        return cls(sinks=[AuditSinkSchema(type="jsonl", path="data/logs/agent.jsonl", rotation="daily")])


class HookSchema(BaseModel):
    event: str
    action: str
    config: dict[str, Any] = {}


class HooksSchema(BaseModel):
    hooks: list[HookSchema] = []


# --- SCM Config ---

_LEGACY_MAP = {
    "GITEA_URL": "SCM_URL",
    "GITEA_TOKEN": "SCM_TOKEN",
    "GITEA_REPO": "SCM_REPO",
    "GITEA_USER": "SCM_USER",
    "GITEA_BOT_USER": "SCM_BOT_USER",
}


class SCMConfig(BaseModel):
    provider: str = "gitea"
    url: str
    token: str
    repo: str
    user: str = ""
    bot_user: str = ""


def load_scm_config() -> SCMConfig:
    if os.environ.get("SCM_PROVIDER") or os.environ.get("SCM_URL"):
        return SCMConfig(
            provider=os.environ.get("SCM_PROVIDER", "gitea"),
            url=os.environ["SCM_URL"],
            token=os.environ["SCM_TOKEN"],
            repo=os.environ["SCM_REPO"],
            user=os.environ.get("SCM_USER", ""),
            bot_user=os.environ.get("SCM_BOT_USER", ""),
        )
    if os.environ.get("GITEA_URL"):
        log.info("Legacy GITEA_* env vars detected, mapping to SCM_*")
        return SCMConfig(
            provider="gitea",
            url=os.environ["GITEA_URL"],
            token=os.environ.get("GITEA_TOKEN", ""),
            repo=os.environ.get("GITEA_REPO", ""),
            user=os.environ.get("GITEA_USER", ""),
            bot_user=os.environ.get("GITEA_BOT_USER", ""),
        )
    raise ValueError(
        "SCM not configured. Set SCM_PROVIDER+SCM_URL+SCM_TOKEN+SCM_REPO "
        "or legacy GITEA_URL+GITEA_TOKEN+GITEA_REPO."
    )


# --- IConfig Implementation ---


class FileConfig(IConfig):
    def __init__(self, config_dir: Path | str):
        self._config_dir = Path(config_dir)
        self._data: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        for json_file in self._config_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    self._data[json_file.stem] = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Failed to load %s: %s", json_file, exc)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        parts = key.split(".")
        current: Any = self._data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return default
            else:
                return default
        return current

    def feature_flag(self, name: str) -> bool:
        return bool(self.get(f"features.{name}", False))

    def reload(self) -> None:
        self._data.clear()
        self._load()


def load_gates_config(config_dir: Path | str) -> GatesConfigSchema:
    path = Path(config_dir) / "gates.json"
    if not path.exists():
        log.info("No gates.json found, using defaults (all gates required)")
        return GatesConfigSchema()
    try:
        with open(path) as f:
            data = json.load(f)
        return GatesConfigSchema(**data)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid gates.json: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Gates config validation failed: {exc}") from exc


def load_eval_config(config_dir: Path | str) -> EvalSchema:
    path = Path(config_dir) / "eval.json"
    if not path.exists():
        log.info("No eval.json found, using defaults")
        return EvalSchema()
    try:
        with open(path) as f:
            data = json.load(f)
        return EvalSchema(**data)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid eval.json: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Eval config validation failed: {exc}") from exc


def load_audit_config(config_dir: Path | str) -> AuditSchema:
    path = Path(config_dir) / "audit.json"
    if not path.exists():
        log.info("No audit.json found, using default JSONL sink")
        return AuditSchema.default()
    try:
        with open(path) as f:
            data = json.load(f)
        return AuditSchema(**data)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid audit.json: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Audit config validation failed: {exc}") from exc
