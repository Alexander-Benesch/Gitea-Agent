from __future__ import annotations

from samuel.core.types import GateContext, GateResult
from samuel.slices.pr_gates.gates import (
    GATE_REGISTRY,
    gate_1_branch_guard,
    gate_2_plan_comment,
    gate_3_metadata_block,
    gate_4_eval_timestamp,
    gate_5_diff_not_empty,
    gate_6_self_consistency,
    gate_7_scope_guard,
    gate_8_slice_gate,
    gate_9_quality_pipeline,
    gate_10_eval_score,
    gate_11_ac_verification,
    gate_12_ready_to_close,
    gate_13a_branch_freshness,
    gate_13b_destructive_diff,
)


def _ctx(**overrides) -> GateContext:
    defaults = {
        "issue_number": 42,
        "branch": "feature/test",
        "changed_files": ["handler.py"],
        "diff": "+new line\n-old line\n",
        "plan_comment": "## Plan\nAgent-Metadaten\n- [ ] [DIFF] handler.py\n### Akzeptanzkriterien\n- [ ] AC1",
        "eval_score": 0.85,
    }
    defaults.update(overrides)
    return GateContext(**defaults)


class TestGate1BranchGuard:
    def test_pass_feature_branch(self):
        assert gate_1_branch_guard(_ctx(branch="feature/test")).passed is True

    def test_fail_main(self):
        assert gate_1_branch_guard(_ctx(branch="main")).passed is False

    def test_fail_master(self):
        assert gate_1_branch_guard(_ctx(branch="master")).passed is False

    def test_fail_empty(self):
        assert gate_1_branch_guard(_ctx(branch="")).passed is False


class TestGate2PlanComment:
    def test_pass_with_plan(self):
        assert gate_2_plan_comment(_ctx()).passed is True

    def test_fail_no_plan(self):
        assert gate_2_plan_comment(_ctx(plan_comment=None)).passed is False

    def test_fail_short_plan(self):
        assert gate_2_plan_comment(_ctx(plan_comment="short")).passed is False


class TestGate3MetadataBlock:
    def test_pass_with_metadata(self):
        assert gate_3_metadata_block(_ctx()).passed is True

    def test_fail_no_metadata(self):
        assert gate_3_metadata_block(_ctx(plan_comment="## Plan\nkein Meta")).passed is False


class TestGate4EvalTimestamp:
    def test_pass_with_score(self):
        assert gate_4_eval_timestamp(_ctx()).passed is True

    def test_fail_no_score(self):
        assert gate_4_eval_timestamp(_ctx(eval_score=None)).passed is False


class TestGate5DiffNotEmpty:
    def test_pass_with_diff(self):
        assert gate_5_diff_not_empty(_ctx()).passed is True

    def test_fail_empty_diff(self):
        assert gate_5_diff_not_empty(_ctx(diff="")).passed is False

    def test_fail_whitespace_diff(self):
        assert gate_5_diff_not_empty(_ctx(diff="   \n  ")).passed is False


class TestGate6SelfConsistency:
    def test_always_passes(self):
        assert gate_6_self_consistency(_ctx()).passed is True


class TestGate7ScopeGuard:
    def test_pass_normal_files(self):
        assert gate_7_scope_guard(_ctx()).passed is True

    def test_fail_env_file(self):
        assert gate_7_scope_guard(_ctx(changed_files=[".env"])).passed is False

    def test_fail_secrets(self):
        assert gate_7_scope_guard(_ctx(changed_files=["secrets.json"])).passed is False

    def test_fail_no_files(self):
        assert gate_7_scope_guard(_ctx(changed_files=[])).passed is False

    def test_owasp_risk_on_failure(self):
        result = gate_7_scope_guard(_ctx(changed_files=[".env"]))
        assert result.owasp_risk == "A01:2021"


class TestGate8SliceGate:
    def test_always_passes(self):
        assert gate_8_slice_gate(_ctx()).passed is True


class TestGate9QualityPipeline:
    def test_always_passes(self):
        assert gate_9_quality_pipeline(_ctx()).passed is True


class TestGate10EvalScore:
    def test_pass_high_score(self):
        assert gate_10_eval_score(_ctx(eval_score=0.85)).passed is True

    def test_fail_low_score(self):
        assert gate_10_eval_score(_ctx(eval_score=0.3)).passed is False

    def test_fail_no_score(self):
        assert gate_10_eval_score(_ctx(eval_score=None)).passed is False


class TestGate11ACVerification:
    def test_pass_with_acs(self):
        assert gate_11_ac_verification(_ctx()).passed is True

    def test_fail_no_plan(self):
        assert gate_11_ac_verification(_ctx(plan_comment=None)).passed is False

    def test_fail_no_acs_in_plan(self):
        assert gate_11_ac_verification(_ctx(plan_comment="## Plan\nJust text")).passed is False


class TestGate12ReadyToClose:
    def test_fail_unchecked_acs(self):
        assert gate_12_ready_to_close(_ctx()).passed is False

    def test_pass_all_checked(self):
        plan = "## Plan\n- [x] AC1\n- [x] AC2"
        assert gate_12_ready_to_close(_ctx(plan_comment=plan)).passed is True

    def test_pass_no_plan(self):
        assert gate_12_ready_to_close(_ctx(plan_comment=None)).passed is True

    def test_pass_no_acs(self):
        assert gate_12_ready_to_close(_ctx(plan_comment="Just a plan")).passed is True


class TestGate13aBranchFreshness:
    def test_default_passes(self):
        assert gate_13a_branch_freshness(_ctx()).passed is True


class TestGate13bDestructiveDiff:
    def test_pass_normal_diff(self):
        assert gate_13b_destructive_diff(_ctx()).passed is True

    def test_pass_no_diff(self):
        assert gate_13b_destructive_diff(_ctx(diff="")).passed is True

    def test_fail_massive_deletion(self):
        diff = "\n".join([f"-deleted line {i}" for i in range(200)])
        diff += "\n+one added line"
        assert gate_13b_destructive_diff(_ctx(diff=diff)).passed is False


class TestGateRegistry:
    def test_all_14_gates_registered(self):
        expected = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "13a", "13b"}
        assert set(GATE_REGISTRY.keys()) == expected

    def test_all_gates_return_gate_result(self):
        ctx = _ctx()
        for gate_id, fn in GATE_REGISTRY.items():
            result = fn(ctx)
            assert isinstance(result, GateResult), f"Gate {gate_id} returned {type(result)}"
