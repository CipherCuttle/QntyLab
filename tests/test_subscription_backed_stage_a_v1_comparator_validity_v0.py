"""Focused tests for the Stage-A V1 comparison-validity layer.

These tests are deterministic and never touch the historical task, the
measured product workers, or any network. They exist to machine-prove the
frozen classification matrix and the predispatch negative control before the
single authorized episode is dispatched.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from qntylab.subscription_backed_stage_a_v1 import DSH_ARM, NATIVE_ARM
from qntylab.subscription_backed_stage_a_v1_comparator_validity_v0 import (
    AMENDMENT_ID,
    CANONICAL_PR131_MERGE,
    CLASSIFICATION_FAIL,
    CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT,
    CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY,
    CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE,
    CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE,
    PASS_CLASSIFICATIONS,
    PRECEDENCE,
    ArmScorerResult,
    ComparisonEvidence,
    FailClosed,
    classify,
    comparison_valid,
)

REPAIR_DIR = pathlib.Path(
    "experiments/research/qnty_agent_orchestration_control_contract_v0"
    "/subscription_backed_stage_a_v1/comparator_validity_repair_v0"
)
V1_DIR = REPAIR_DIR.parent


def arm(arm_id, correctness, intervention, **overrides):
    values = {
        "arm_id": arm_id,
        "receipt_sealed": True,
        "scorer_result_present": True,
        "correctness_score": correctness,
        "human_intervention_count": intervention,
    }
    values.update(overrides)
    return ArmScorerResult(**values)


def evidence(t_corr, n_corr, t_int=0, n_int=0, treatment=None, baseline=None, **overrides):
    return ComparisonEvidence(
        treatment=treatment or arm(DSH_ARM, t_corr, t_int),
        baseline=baseline or arm(NATIVE_ARM, n_corr, n_int),
        **overrides,
    )


# --------------------------------------------------------------------------
# Frozen classification matrix
# --------------------------------------------------------------------------


def test_zero_zero_is_invalid_benchmark_not_pass_and_not_fail():
    result = classify(evidence(0, 0))
    assert result == CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT
    assert result not in PASS_CLASSIFICATIONS
    assert result != CLASSIFICATION_FAIL


def test_treatment_zero_baseline_one_is_fail():
    assert classify(evidence(0, 1)) == CLASSIFICATION_FAIL


def test_treatment_one_baseline_zero_passes_when_intervention_does_not_regress():
    assert classify(evidence(1, 0, t_int=0, n_int=0)) == CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE
    assert classify(evidence(1, 0, t_int=1, n_int=2)) == CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE
    assert classify(evidence(1, 0, t_int=2, n_int=2)) == CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE


def test_treatment_one_baseline_zero_fails_when_intervention_regresses():
    assert classify(evidence(1, 0, t_int=2, n_int=1)) == CLASSIFICATION_FAIL


def test_one_one_equal_intervention_is_pass_no_incremental_value():
    assert classify(evidence(1, 1, t_int=3, n_int=3)) == CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE


def test_one_one_lower_treatment_intervention_is_pass_with_incremental_value():
    assert classify(evidence(1, 1, t_int=1, n_int=3)) == CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE


def test_one_one_higher_treatment_intervention_is_fail():
    assert classify(evidence(1, 1, t_int=4, n_int=3)) == CLASSIFICATION_FAIL


def test_full_matrix_is_exhaustively_frozen():
    expected = {
        (0, 0, "lower"): CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT,
        (0, 0, "equal"): CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT,
        (0, 0, "higher"): CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT,
        (0, 1, "lower"): CLASSIFICATION_FAIL,
        (0, 1, "equal"): CLASSIFICATION_FAIL,
        (0, 1, "higher"): CLASSIFICATION_FAIL,
        (1, 0, "lower"): CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE,
        (1, 0, "equal"): CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE,
        (1, 0, "higher"): CLASSIFICATION_FAIL,
        (1, 1, "lower"): CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE,
        (1, 1, "equal"): CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE,
        (1, 1, "higher"): CLASSIFICATION_FAIL,
    }
    interventions = {"lower": (1, 2), "equal": (2, 2), "higher": (3, 2)}
    for (t_corr, n_corr, relation), want in expected.items():
        t_int, n_int = interventions[relation]
        got = classify(evidence(t_corr, n_corr, t_int=t_int, n_int=n_int))
        assert got == want, f"{t_corr}/{n_corr} intervention {relation}: {got} != {want}"


# --------------------------------------------------------------------------
# Predispatch negative control
# --------------------------------------------------------------------------


def test_zero_zero_pass_is_unreachable_across_every_clean_intervention_pair():
    for t_int in range(0, 5):
        for n_int in range(0, 5):
            result = classify(evidence(0, 0, t_int=t_int, n_int=n_int))
            assert result not in PASS_CLASSIFICATIONS
            assert result != CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE
            assert result != CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE
            assert result == CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT


def test_no_pass_path_exists_when_both_correctness_scores_are_zero():
    """Exhaustive sweep of every evidence shape reachable with 0/0 correctness."""
    for t_int in range(0, 3):
        for n_int in range(0, 3):
            for capacity in ((), ("SUBSCRIPTION_THROTTLED",)):
                for gates in ((), ("PAY_PER_TOKEN_MODEL_API_USED",)):
                    ev = ComparisonEvidence(
                        treatment=arm(
                            DSH_ARM, 0, t_int,
                            capacity_invalidation_events=capacity,
                            measured_hard_gate_failures=gates,
                        ),
                        baseline=arm(NATIVE_ARM, 0, n_int),
                    )
                    assert classify(ev) not in PASS_CLASSIFICATIONS


def test_comparison_validity_predicate_requires_at_least_one_correct_arm():
    assert comparison_valid(evidence(0, 0)) is False
    assert comparison_valid(evidence(1, 0)) is True
    assert comparison_valid(evidence(0, 1)) is True
    assert comparison_valid(evidence(1, 1)) is True


def test_predicate_does_not_require_the_baseline_to_be_correct():
    """DSH correct / native incorrect stays a VALID comparison, never INVALID."""
    ev = evidence(1, 0)
    assert comparison_valid(ev) is True
    assert classify(ev) != CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT
    assert classify(ev) == CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE


# --------------------------------------------------------------------------
# Precedence
# --------------------------------------------------------------------------


def test_capacity_invalidation_outranks_comparator_classification():
    for t_corr, n_corr in ((0, 0), (0, 1), (1, 0), (1, 1)):
        ev = ComparisonEvidence(
            treatment=arm(
                DSH_ARM, t_corr, 0, capacity_invalidation_events=("SUBSCRIPTION_THROTTLED",)
            ),
            baseline=arm(NATIVE_ARM, n_corr, 0),
        )
        assert classify(ev) == CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY


def test_capacity_asymmetry_on_either_arm_invalidates_the_episode():
    baseline_throttled = ComparisonEvidence(
        treatment=arm(DSH_ARM, 1, 0),
        baseline=arm(
            NATIVE_ARM, 0, 0, capacity_invalidation_events=("SUBSCRIPTION_THROTTLED",)
        ),
    )
    assert classify(baseline_throttled) == CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY


def test_capacity_invalidation_is_not_benchmark_invalidity():
    capacity = ComparisonEvidence(
        treatment=arm(
            DSH_ARM, 0, 0, capacity_invalidation_events=("SUBSCRIPTION_THROTTLED",)
        ),
        baseline=arm(NATIVE_ARM, 0, 0),
    )
    assert classify(capacity) == CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY
    assert classify(evidence(0, 0)) == CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT
    assert (
        CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY
        != CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT
    )


def test_measured_hard_gate_failure_outranks_every_comparator_outcome():
    for t_corr, n_corr in ((0, 0), (0, 1), (1, 0), (1, 1)):
        ev = ComparisonEvidence(
            treatment=arm(
                DSH_ARM, t_corr, 0, measured_hard_gate_failures=("UNAUTHORIZED_WRITES",)
            ),
            baseline=arm(NATIVE_ARM, n_corr, 0),
        )
        assert classify(ev) == CLASSIFICATION_FAIL


def test_precedence_is_frozen_and_ordered():
    assert PRECEDENCE == (
        "R1_AUTHORITY_FIREWALL_OR_UNSEALED_RECEIPT_FAIL_CLOSED",
        "R2_MEASURED_HARD_GATE_FAILURE",
        "R3_ENVIRONMENT_OR_PRODUCT_CAPACITY_INVALIDATION",
        "R4_MISSING_OR_MALFORMED_SCORER_EVIDENCE_FAIL_CLOSED",
        "R5_BOTH_ARMS_INCORRECT_BENCHMARK_INVALID",
        "R6_PRIMARY_NONINFERIORITY_RULES",
    )


# --------------------------------------------------------------------------
# Fail-closed behaviour
# --------------------------------------------------------------------------


def test_missing_scorer_evidence_fails_closed_and_is_never_read_as_zero():
    missing = ComparisonEvidence(
        treatment=ArmScorerResult(
            arm_id=DSH_ARM,
            receipt_sealed=True,
            scorer_result_present=False,
            correctness_score=None,
            human_intervention_count=None,
        ),
        baseline=arm(NATIVE_ARM, 0, 0),
    )
    with pytest.raises(FailClosed, match="missing, out of range, or ambiguous"):
        classify(missing)


def test_absent_correctness_score_does_not_enter_benchmark_invalid():
    both_absent = ComparisonEvidence(
        treatment=ArmScorerResult(DSH_ARM, True, False),
        baseline=ArmScorerResult(NATIVE_ARM, True, False),
    )
    with pytest.raises(FailClosed):
        classify(both_absent)
    assert comparison_valid(both_absent) is False


def test_unsealed_receipt_fails_closed_and_is_never_incorrect_zero():
    for unsealed_arm in ("treatment", "baseline"):
        kwargs = {
            "treatment": arm(DSH_ARM, 1, 0, receipt_sealed=unsealed_arm != "treatment"),
            "baseline": arm(NATIVE_ARM, 1, 0, receipt_sealed=unsealed_arm != "baseline"),
        }
        with pytest.raises(FailClosed, match="unsealed"):
            classify(ComparisonEvidence(**kwargs))


def test_ambiguous_intervention_event_fails_closed():
    ambiguous = ComparisonEvidence(
        treatment=arm(DSH_ARM, 1, 1, ambiguous_intervention_event=True),
        baseline=arm(NATIVE_ARM, 1, 1),
    )
    with pytest.raises(FailClosed):
        classify(ambiguous)


def test_out_of_range_correctness_score_fails_closed():
    for bad in (-1, 2, 0.5, True, "1"):
        bad_arm = ComparisonEvidence(
            treatment=arm(DSH_ARM, bad, 0),
            baseline=arm(NATIVE_ARM, 1, 0),
        )
        with pytest.raises(FailClosed):
            classify(bad_arm)


def test_negative_or_non_integer_intervention_count_fails_closed():
    for bad in (-1, None, 1.5, "2", True):
        ev = ComparisonEvidence(
            treatment=arm(DSH_ARM, 1, bad),
            baseline=arm(NATIVE_ARM, 1, 0),
        )
        with pytest.raises(FailClosed):
            classify(ev)


def test_branch_local_amendment_cannot_self_authorize_the_repaired_interpretation():
    with pytest.raises(FailClosed, match="branch-local"):
        classify(evidence(1, 1, comparator_validity_amendment_canonical=False))


def test_answer_key_firewall_breach_fails_closed():
    with pytest.raises(FailClosed, match="answer-key firewall"):
        classify(evidence(1, 1, answer_key_firewall_passed=False))


def test_swapped_arm_identity_fails_closed():
    swapped = ComparisonEvidence(
        treatment=arm(NATIVE_ARM, 1, 0),
        baseline=arm(DSH_ARM, 0, 0),
    )
    with pytest.raises(FailClosed, match="treatment arm identity"):
        classify(swapped)


# --------------------------------------------------------------------------
# Frozen artifact bindings
# --------------------------------------------------------------------------


def test_amendment_binds_canonical_pr131_and_leaves_every_digest_unchanged():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    prereg = json.loads((V1_DIR / "preregistration.json").read_text())
    binding = amendment["binding"]

    assert amendment["amendment_id"] == AMENDMENT_ID
    assert binding["canonical_pr_131_merge"] == CANONICAL_PR131_MERGE
    assert binding["pr_131_frozen_candidate_parent"] == "c952f31e6ebdbb04bd3934e05705264cfe4b88a9"
    assert amendment["amended_experiment"] == prereg["experiment_id"]

    fixture = prereg["historical_fixture"]
    assert binding["task_digest"] == fixture["task_digest"]
    assert binding["scorer_digest"] == fixture["scorer_digest"]
    assert binding["intervention_digest"] == fixture["intervention_digest"]
    assert binding["historical_base"] == fixture["base"]
    assert binding["gate_digest"] == prereg["gate_digest"]
    assert binding["receipt_digest"] == prereg["receipt_digest"]
    assert binding["controller_contract_digest"] == prereg["controller_contract_digest"]

    unchanged = amendment["unchanged_identities"]
    assert unchanged["binary_correctness_function_changed"] is False
    assert unchanged["scoring_propositions_changed"] is False
    assert unchanged["product_identities_changed"] is False
    assert unchanged["arm_order_changed"] is False
    assert unchanged["answer_key_firewall_changed"] is False
    assert unchanged["zero_fee_rule_changed"] is False
    assert amendment["amendment_type"] == "APPEND_ONLY_INTERPRETATION_NARROWING"
    assert amendment["history_rewritten"] is False
    assert amendment["historical_v1_artifacts_unchanged"] is True


def test_amendment_digests_still_match_the_canonical_files_on_disk():
    import hashlib

    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    binding = amendment["binding"]
    v0_dir = V1_DIR.parent / "stage_a_dsh_shadow_evaluation_preregistration_v0"
    for key, path in (
        ("task_digest", v0_dir / "task_contract.json"),
        ("scorer_digest", v0_dir / "scoring_contract.json"),
        ("intervention_digest", v0_dir / "intervention_schema.json"),
        ("gate_digest", V1_DIR / "gate_schema.json"),
        ("receipt_digest", V1_DIR / "receipt_schema.json"),
        ("controller_contract_digest", V1_DIR / "controller_contract.json"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding[key], path


def test_amendment_records_the_predispatch_timing_invariant():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    timing = amendment["predispatch_timing_invariant"]
    assert timing["v1_treatment_dispatch_count"] == 0
    assert timing["v1_baseline_dispatch_count"] == 0
    assert timing["v1_episode_consumed"] is False
    assert timing["answer_key_released"] is False
    assert timing["empirical_scoring"] is False
    assert timing["execution_receipt_exists"] is False
    assert timing["amendment_is_pre_dispatch"] is True
    assert timing["post_dispatch_comparator_mutation"] is False


def test_amendment_matrix_agrees_with_the_implementation():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    matrix = amendment["classification_matrix"]
    assert matrix["0_0"] == classify(evidence(0, 0))
    assert matrix["0_1"] == classify(evidence(0, 1))
    assert matrix["1_0_treatment_intervention_le_baseline"] == classify(evidence(1, 0, 1, 1))
    assert matrix["1_0_treatment_intervention_gt_baseline"] == classify(evidence(1, 0, 2, 1))
    assert matrix["1_1_treatment_intervention_lt_baseline"] == classify(evidence(1, 1, 1, 2))
    assert matrix["1_1_treatment_intervention_eq_baseline"] == classify(evidence(1, 1, 2, 2))
    assert matrix["1_1_treatment_intervention_gt_baseline"] == classify(evidence(1, 1, 3, 2))
    assert amendment["negative_control"]["zero_zero_pass_reachable"] is False


def test_amendment_precedence_ranks_match_the_implementation():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    ranks = amendment["classification_precedence"]["ranks"]
    assert tuple(rank["id"] for rank in ranks) == PRECEDENCE
    assert [rank["rank"] for rank in ranks] == list(range(1, len(PRECEDENCE) + 1))
    assert amendment["classification_precedence"]["reordering_after_results_allowed"] is False


# --------------------------------------------------------------------------
# Authorization amendment
# --------------------------------------------------------------------------


def test_authorization_amendment_adds_no_second_episode():
    auth = json.loads((REPAIR_DIR / "execution_authorization_amendment.json").read_text())
    prior = json.loads((V1_DIR / "execution_authorization.json").read_text())

    assert auth["authorized_episode_count_after_repair"] == 1
    assert auth["cumulative_authorized_episode_count"] == 1
    assert auth["authorized_episode_count_after_repair"] == prior["authorized_episode_count"]
    assert auth["additional_episode_added"] is False
    assert auth["second_episode_allowed"] is False
    assert auth["prior_episode_consumption"] == 0
    assert auth["amends"]["prior_authorized_episode_count"] == 1
    assert auth["amends"]["prior_episode_consumption"] == 0
    assert auth["amends"]["prior_authorization_bytes_changed"] is False
    assert auth["authorized_experiment"] == prior["authorized_experiment"]
    assert auth["authorized_arm_count"] == prior["authorized_arm_count"]


def test_authorization_amendment_is_effective_only_after_canonical_merge():
    auth = json.loads((REPAIR_DIR / "execution_authorization_amendment.json").read_text())
    effectiveness = auth["effectiveness"]
    assert auth["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert effectiveness["branch_local_execution_authorized"] is False
    assert effectiveness["effective_only_after_canonical_merge"] is True
    assert effectiveness["branch_local_candidate_cannot_self_authorize"] is True
    assert auth["requires"]["comparator_validity_amendment_canonical"] is True
    assert auth["requires"]["canonical_pr_131_merge_present"] == CANONICAL_PR131_MERGE


def test_authorization_amendment_preserves_every_frozen_boundary():
    auth = json.loads((REPAIR_DIR / "execution_authorization_amendment.json").read_text())
    preserved = auth["preserved_boundaries"]
    assert preserved["zero_fee_contract_preserved"] is True
    assert preserved["pay_per_token_model_api_keys_allowed"] is False
    assert preserved["openai_api_key_allowed"] is False
    assert preserved["anthropic_api_key_allowed"] is False
    assert preserved["deepseek_api_key_allowed"] is False
    assert preserved["other_model_api_key_allowed"] is False
    assert preserved["answer_key_firewall_preserved"] is True
    assert preserved["role_mapping_preserved"] is True
    assert preserved["product_identities_preserved"] is True
    assert preserved["retry_ceilings_preserved"] is True
    assert preserved["dsh_arm_first_native_arm_second"] is True
    assert preserved["arm_1"] == "DSH_TREATMENT"
    assert preserved["arm_2"] == "NATIVE_BASELINE"
    assert auth["rescue_rerun_allowed"] is False
    assert auth["no_rescue_rerun_after_invalid_benchmark"] is True
    assert auth["no_rescue_rerun_after_capacity_failure"] is True


def test_repair_creates_no_runtime_trading_or_capital_authority():
    for path in ("amendment.json", "execution_authorization_amendment.json"):
        ceiling = json.loads((REPAIR_DIR / path).read_text())["authority_ceiling"]
        assert ceiling["current_max_autonomy"] == "L0_SHADOW"
        assert ceiling["runtime_implementation_authorized"] is False
        assert ceiling["dsh_runtime_implementation_authorized"] is False
        assert ceiling["qnty_next_action_authority"] == "NONE"
        assert ceiling["trading_authority"] == "NONE"
        assert ceiling["capital_authority"] == "NONE"
        assert ceiling["auto_merge_authorized"] is False


def test_new_classification_grants_nothing_and_forbids_rescue_rerun():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    new = amendment["new_classification"]
    assert new["classification_id"] == CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT
    assert new["is_pass"] is False
    assert new["is_fail"] is False
    assert new["grants_any_authority"] is False
    assert new["grants_runtime_authority"] is False
    assert new["grants_rerun"] is False
    assert new["rescue_rerun_allowed"] is False
    assert new["consumes_authorized_episode_if_reached_after_dispatch"] is True


def test_frozen_v1_outcome_vocabulary_is_extended_not_replaced():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    prereg = json.loads((V1_DIR / "preregistration.json").read_text())
    after = amendment["outcomes_after_amendment"]
    assert set(prereg["outcomes_frozen_before_execution"]).issubset(set(after))
    assert amendment["outcomes_removed"] == []
    assert set(after) - set(prereg["outcomes_frozen_before_execution"]) == {
        CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT
    }


def test_scorer_binary_function_is_untouched_by_the_repair():
    amendment = json.loads((REPAIR_DIR / "amendment.json").read_text())
    scorer = amendment["scorer_unchanged"]
    assert scorer["binary_correctness_function_changed"] is False
    assert scorer["partial_correctness_weights_introduced"] is False
    assert scorer["score_zero_remains_legal"] is True
    assert scorer["propositions_changed"] is False
