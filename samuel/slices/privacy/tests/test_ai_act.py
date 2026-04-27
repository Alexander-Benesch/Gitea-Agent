from __future__ import annotations

from samuel.slices.privacy.ai_act import (
    ai_attribution_trailer,
    enrich_llm_event_payload,
    get_risk_classification,
)


class TestAIAttribution:
    def test_trailer_with_version(self):
        trailer = ai_attribution_trailer("claude-3.5-sonnet", "20240620")
        assert trailer == "AI-Generated-By: claude-3.5-sonnet@20240620"

    def test_trailer_without_version(self):
        trailer = ai_attribution_trailer("ollama/codellama")
        assert trailer == "AI-Generated-By: ollama/codellama"

    def test_trailer_format_machine_readable(self):
        trailer = ai_attribution_trailer("deepseek-coder", "v2")
        assert trailer.startswith("AI-Generated-By: ")
        assert ":" in trailer


class TestEnrichLLMEvent:
    def test_adds_prompt_hash(self):
        payload = enrich_llm_event_payload(
            {"issue": 42},
            prompt="Generate a function",
        )

        assert "prompt_hash" in payload
        assert len(payload["prompt_hash"]) == 16
        assert payload["issue"] == 42

    def test_adds_all_fields(self):
        payload = enrich_llm_event_payload(
            {},
            prompt="test",
            system_prompt_version="v3.2",
            temperature=0.7,
            model_version="claude-3.5-sonnet-20240620",
        )

        assert payload["prompt_hash"] is not None
        assert payload["system_prompt_version"] == "v3.2"
        assert payload["temperature"] == 0.7
        assert payload["model_version"] == "claude-3.5-sonnet-20240620"

    def test_preserves_existing_payload(self):
        payload = enrich_llm_event_payload(
            {"issue": 42, "correlation_id": "abc"},
            prompt="test",
        )

        assert payload["issue"] == 42
        assert payload["correlation_id"] == "abc"

    def test_empty_prompt_no_hash(self):
        payload = enrich_llm_event_payload({})
        assert "prompt_hash" not in payload

    def test_consistent_hash(self):
        p1 = enrich_llm_event_payload({}, prompt="same prompt")
        p2 = enrich_llm_event_payload({}, prompt="same prompt")
        assert p1["prompt_hash"] == p2["prompt_hash"]


class TestRiskClassification:
    def test_classification_is_limited_risk(self):
        rc = get_risk_classification()
        assert rc["classification"] == "Limited Risk"

    def test_has_article_reference(self):
        rc = get_risk_classification()
        assert "Art. 6" in rc["article"]
        assert "Art. 50" in rc["article"]

    def test_has_justification(self):
        rc = get_risk_classification()
        assert len(rc["justification"]) > 100
        assert "Annex III" in rc["justification"]

    def test_has_transparency_measures(self):
        rc = get_risk_classification()
        assert len(rc["transparency_measures"]) >= 3
        assert any("AI-Generated-By" in m for m in rc["transparency_measures"])

    def test_has_human_oversight(self):
        rc = get_risk_classification()
        assert len(rc["human_oversight"]) >= 3
        assert any("Gate" in m for m in rc["human_oversight"])
