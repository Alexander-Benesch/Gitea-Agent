from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from samuel.core.events import AuditEvent
from samuel.slices.audit_trail.owasp import classify as _owasp_risk

log = logging.getLogger(__name__)

_bus: Any = None
_correlation_id: str | None = None
_jsonl_path: Path = Path("data/logs/agent.jsonl")


def set_bus(bus: Any) -> None:
    global _bus
    _bus = bus


def set_correlation_id(cid: str) -> None:
    global _correlation_id
    _correlation_id = cid


def set_jsonl_path(path: Path | str) -> None:
    global _jsonl_path
    _jsonl_path = Path(path)


def log_event(
    evt: str,
    cat: str,
    msg: str,
    *,
    lvl: str = "info",
    issue: int = 0,
    step: str = "",
    branch: str = "",
    trigger: str = "",
    source: str = "",
    caused_by: str = "",
    parent_evt: str = "",
    meta: dict | None = None,
) -> str:
    event_id = str(uuid4())
    correlation_id = _correlation_id or str(uuid4())
    owasp = _owasp_risk(cat, evt)

    payload = {
        "evt": evt,
        "cat": cat,
        "msg": msg,
        "lvl": lvl,
        "issue": issue,
        "step": step,
        "branch": branch,
        "trigger": trigger,
        "source": source,
        "caused_by": caused_by,
        "parent_evt": parent_evt,
        "meta": meta or {},
        "owasp_risk": owasp,
        "event_id": event_id,
    }

    if _bus is not None:
        event = AuditEvent(
            payload=payload,
            correlation_id=correlation_id,
            causation_id=caused_by or None,
        )
        _bus.publish(event)
        return event_id

    return _write_jsonl(event_id, correlation_id, payload)


def _write_jsonl(event_id: str, correlation_id: str, payload: dict) -> str:
    record = {
        "id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        **payload,
    }
    try:
        _jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        log.exception("Failed to write audit JSONL")
    return event_id
