from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus

log = logging.getLogger(__name__)


class SequenceHandler:
    def __init__(
        self,
        bus: Bus,
        *,
        mode: str = "warn",
        patterns_path: Path | str | None = None,
    ) -> None:
        self._bus = bus
        self._mode = mode
        self._patterns_path = Path(patterns_path) if patterns_path else None
        self._event_log: list[str] = []
        self._bigrams: Counter[tuple[str, str]] = Counter()
        self._known_patterns: list[dict[str, Any]] = []

        if self._patterns_path and self._patterns_path.exists():
            self._load_patterns()

    def record_event(self, event_name: str) -> None:
        if self._event_log:
            prev = self._event_log[-1]
            self._bigrams[(prev, event_name)] += 1
        self._event_log.append(event_name)

    def get_patterns(self, min_count: int = 2) -> list[dict[str, Any]]:
        return [
            {"from": a, "to": b, "count": c}
            for (a, b), c in self._bigrams.most_common()
            if c >= min_count
        ]

    def validate_sequence(self, expected: list[str]) -> dict[str, Any]:
        if not expected:
            return {"valid": True, "violations": []}

        violations: list[str] = []
        for i, exp in enumerate(expected):
            if i >= len(self._event_log):
                violations.append(f"step {i}: expected {exp}, got nothing")
            elif self._event_log[i] != exp:
                violations.append(f"step {i}: expected {exp}, got {self._event_log[i]}")

        result = {"valid": len(violations) == 0, "violations": violations}

        if not result["valid"] and self._mode == "block":
            from samuel.core.events import Event
            self._bus.publish(Event(
                name="SequenceViolation",
                payload={"violations": violations, "mode": self._mode},
            ))

        return result

    def save_patterns(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path else self._patterns_path
        if target is None:
            raise ValueError("No patterns_path configured")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 2,
            "source": "v2",
            "patterns": self.get_patterns(min_count=1),
        }
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        log.info("Saved %d patterns to %s", len(data["patterns"]), target)
        return target

    def _load_patterns(self) -> None:
        assert self._patterns_path is not None
        try:
            data = json.loads(self._patterns_path.read_text())
            self._known_patterns = data.get("patterns", [])
            for p in self._known_patterns:
                key = (p["from"], p["to"])
                self._bigrams[key] = max(self._bigrams[key], p.get("count", 1))
            log.info(
                "Loaded %d patterns from %s (version=%s)",
                len(self._known_patterns),
                self._patterns_path,
                data.get("version", "?"),
            )
        except (json.JSONDecodeError, KeyError):
            log.warning("Could not load patterns from %s", self._patterns_path)

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("warn", "block", "off"):
            raise ValueError(f"Invalid mode: {value!r} (expected warn/block/off)")
        self._mode = value

    def get_log(self) -> list[str]:
        return list(self._event_log)

    def clear(self) -> None:
        self._event_log.clear()
        self._bigrams.clear()
