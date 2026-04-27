from __future__ import annotations

import json
from pathlib import Path

import pytest

from samuel.core.bus import Bus
from samuel.slices.sequence.handler import SequenceHandler


class TestRecordEvent:
    def test_record_single_event(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("IssueReady")

        assert handler.get_log() == ["IssueReady"]

    def test_record_multiple_events_creates_bigrams(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("IssueReady")
        handler.record_event("PlanCreated")
        handler.record_event("PlanValidated")

        log = handler.get_log()
        assert log == ["IssueReady", "PlanCreated", "PlanValidated"]


class TestGetPatterns:
    def test_patterns_with_min_count(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        # Create a repeated bigram: A -> B appears 3 times
        for _ in range(3):
            handler.record_event("A")
            handler.record_event("B")

        patterns = handler.get_patterns(min_count=2)

        assert len(patterns) >= 1
        ab = [p for p in patterns if p["from"] == "A" and p["to"] == "B"]
        assert len(ab) == 1
        assert ab[0]["count"] == 3

    def test_patterns_below_min_count_excluded(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("X")
        handler.record_event("Y")  # X->Y appears once

        patterns = handler.get_patterns(min_count=2)

        assert patterns == []

    def test_patterns_default_min_count_is_2(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("A")
        handler.record_event("B")  # only once

        assert handler.get_patterns() == []


class TestValidateSequence:
    def test_valid_sequence(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("Step1")
        handler.record_event("Step2")
        handler.record_event("Step3")

        result = handler.validate_sequence(["Step1", "Step2", "Step3"])

        assert result["valid"] is True
        assert result["violations"] == []

    def test_invalid_sequence_wrong_event(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("Step1")
        handler.record_event("Wrong")

        result = handler.validate_sequence(["Step1", "Step2"])

        assert result["valid"] is False
        assert len(result["violations"]) == 1
        assert "expected Step2" in result["violations"][0]
        assert "got Wrong" in result["violations"][0]

    def test_invalid_sequence_missing_events(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("Step1")

        result = handler.validate_sequence(["Step1", "Step2", "Step3"])

        assert result["valid"] is False
        assert len(result["violations"]) == 2

    def test_empty_expected_is_valid(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        result = handler.validate_sequence([])

        assert result["valid"] is True


class TestClear:
    def test_clear_resets_log_and_bigrams(self):
        bus = Bus()
        handler = SequenceHandler(bus)

        handler.record_event("A")
        handler.record_event("B")
        handler.record_event("A")
        handler.record_event("B")

        handler.clear()

        assert handler.get_log() == []
        assert handler.get_patterns(min_count=1) == []


class TestPatternPersistence:
    def test_save_and_load_patterns(self, tmp_path: Path):
        bus = Bus()
        patterns_file = tmp_path / "repo_patterns.json"

        h1 = SequenceHandler(bus, patterns_path=patterns_file)
        for _ in range(3):
            h1.record_event("A")
            h1.record_event("B")
        h1.save_patterns()

        assert patterns_file.exists()
        data = json.loads(patterns_file.read_text())
        assert data["version"] == 2
        assert data["source"] == "v2"
        assert len(data["patterns"]) >= 1

        h2 = SequenceHandler(Bus(), patterns_path=patterns_file)
        patterns = h2.get_patterns(min_count=2)
        ab = [p for p in patterns if p["from"] == "A" and p["to"] == "B"]
        assert len(ab) == 1
        assert ab[0]["count"] == 3

    def test_load_nonexistent_is_noop(self, tmp_path: Path):
        bus = Bus()
        h = SequenceHandler(bus, patterns_path=tmp_path / "missing.json")
        assert h.get_patterns(min_count=1) == []

    def test_save_without_path_raises(self):
        bus = Bus()
        h = SequenceHandler(bus)
        with pytest.raises(ValueError, match="No patterns_path"):
            h.save_patterns()


class TestValidatorMode:
    def test_default_mode_is_warn(self):
        h = SequenceHandler(Bus())
        assert h.mode == "warn"

    def test_block_mode_publishes_event(self):
        bus = Bus()
        events: list = []
        bus.subscribe("SequenceViolation", lambda ev: events.append(ev))

        h = SequenceHandler(bus, mode="block")
        h.record_event("Step1")
        h.validate_sequence(["Step1", "Step2"])

        assert len(events) == 1
        assert events[0].payload["mode"] == "block"

    def test_warn_mode_no_event(self):
        bus = Bus()
        events: list = []
        bus.subscribe("SequenceViolation", lambda ev: events.append(ev))

        h = SequenceHandler(bus, mode="warn")
        h.record_event("Step1")
        h.validate_sequence(["Step1", "Step2"])

        assert len(events) == 0

    def test_invalid_mode_raises(self):
        h = SequenceHandler(Bus())
        with pytest.raises(ValueError, match="Invalid mode"):
            h.mode = "invalid"

    def test_set_mode(self):
        h = SequenceHandler(Bus(), mode="warn")
        h.mode = "block"
        assert h.mode == "block"
        h.mode = "off"
        assert h.mode == "off"
