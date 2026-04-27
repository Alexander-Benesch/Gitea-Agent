from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import ChangelogCommand, Command
from samuel.core.ports import IVersionControl

log = logging.getLogger(__name__)


class ChangelogHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ChangelogCommand)

        entries: list[dict[str, str]] = cmd.payload.get("entries", [])

        if not entries:
            return {"generated": False, "reason": "no entries"}

        lines = ["# Changelog", ""]
        for entry in entries:
            issue = entry.get("issue", "")
            title = entry.get("title", "")
            category = entry.get("category", "feature")
            prefix = {"feature": "feat", "fix": "fix", "refactor": "refactor"}.get(category, category)
            lines.append(f"- **{prefix}:** {title} (#{issue})")

        body = "\n".join(lines)

        if self._scm and cmd.payload.get("post_to_issue"):
            issue_number = int(cmd.payload["post_to_issue"])
            self._scm.post_comment(issue_number, body)

        return {"generated": True, "changelog": body, "entry_count": len(entries)}
