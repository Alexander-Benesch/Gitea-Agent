from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from samuel.adapters.audit.upcasters import upcast
from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery

log = logging.getLogger(__name__)


class JSONLAuditSink(IAuditSink):
    def __init__(self, path: Path | str, rotation: str = "daily"):
        self._base_path = Path(path)
        self._rotation = rotation

    def _current_path(self) -> Path:
        if self._rotation == "daily":
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            stem = self._base_path.stem
            suffix = self._base_path.suffix or ".jsonl"
            return self._base_path.parent / f"{stem}_{date_str}{suffix}"
        return self._base_path

    def write(self, event: Any) -> None:
        path = self._current_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = event if isinstance(event, dict) else {"data": str(event)}
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def query(self, query: AuditQuery) -> list[Any]:
        results: list[dict] = []
        for path in sorted(self._base_path.parent.glob(f"{self._base_path.stem}*{self._base_path.suffix or '.jsonl'}")):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    record = upcast(json.loads(line))
                    if self._matches(record, query):
                        results.append(record)
                        if len(results) >= query.limit:
                            return results
            except (json.JSONDecodeError, OSError):
                log.warning("Failed to read %s", path)
        return results

    def _matches(self, record: dict, query: AuditQuery) -> bool:
        if query.issue is not None:
            rec_issue = record.get("payload", {}).get("issue") or record.get("issue")
            if rec_issue != query.issue:
                return False
        if query.correlation_id is not None:
            if record.get("correlation_id") != query.correlation_id:
                return False
        if query.owasp_risk is not None:
            rec_owasp = record.get("owasp_risk") or record.get("payload", {}).get("owasp_risk")
            if rec_owasp != query.owasp_risk:
                return False
        if query.event_name is not None:
            rec_name = record.get("event_name") or record.get("name")
            if rec_name != query.event_name:
                return False
        if query.since is not None:
            ts = record.get("ts", "")
            if ts and ts < query.since.isoformat():
                return False
        if query.until is not None:
            ts = record.get("ts", "")
            if ts and ts > query.until.isoformat():
                return False
        return True
