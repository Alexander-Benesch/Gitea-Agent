from __future__ import annotations

from samuel.slices.audit_trail.owasp import (
    OWASP_RISK_CAT_FALLBACK,
    OWASP_RISK_MAP,
    classify,
)


def test_classify_exact_match():
    assert classify("scm", "git_commit") == "broken_trust_boundaries"
    assert classify("guard", "quality_check") == "inadequate_sandboxing"
    assert classify("llm", "llm_call") == "unmonitored_activities"


def test_classify_cat_fallback():
    assert classify("llm", "some_unknown_event") == "unmonitored_activities"
    assert classify("security", "unknown") == "unrestricted_agency"


def test_classify_unknown_returns_none():
    assert classify("totally_unknown", "unknown") is None


def test_all_map_values_are_valid_owasp():
    valid = {
        "unrestricted_agency",
        "uncontrolled_behavior",
        "inadequate_sandboxing",
        "broken_trust_boundaries",
        "identity_access_abuse",
        "unmonitored_activities",
        "unsafe_tool_integration",
        "excessive_autonomy",
        "inadequate_feedback_loops",
        "opaque_reasoning",
    }
    for key, val in OWASP_RISK_MAP.items():
        assert val in valid, f"Invalid OWASP risk '{val}' for {key}"
    for key, val in OWASP_RISK_CAT_FALLBACK.items():
        assert val in valid, f"Invalid OWASP fallback '{val}' for {key}"


def test_all_fallback_cats_covered():
    expected_cats = {
        "guard", "llm", "eval", "scm", "workflow", "system",
        "routing", "context", "health", "config", "perf", "error", "security",
    }
    assert set(OWASP_RISK_CAT_FALLBACK.keys()) == expected_cats
