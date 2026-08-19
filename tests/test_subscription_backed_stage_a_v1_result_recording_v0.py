import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
ARTIFACT_ROOT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "subscription_backed_stage_a_v1/execution_result_v0"
)
RESULT = ARTIFACT_ROOT / "execution_result.json"
ATTRIBUTION = ARTIFACT_ROOT / "forensic_attribution.json"
EVIDENCE = ARTIFACT_ROOT / "evidence_manifest.json"
REVIEW = ARTIFACT_ROOT / "hostile_review.md"
PROJECTS = ROOT / "docs/state/projects.toml"
SEALED_REFERENCES = (
    "73a0bacd4b244f9b83967612ad92d4eb474bbcc7",
    "c5ea1b735172527a98febad9c3165fd2e9a4bf77",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_record_permanently_closes_the_single_consumed_v1_episode():
    record = load(RESULT)
    execution = record["execution"]
    invariant = record["no_rerun_invariant"]
    assert record["episode_id"] == "SUBSCRIPTION_BACKED_STAGE_A_V1-1787094263"
    assert execution["episode_consumed"] is True
    assert execution["authorized_episode_count"] == 1
    assert record["result_recorded"] is True
    assert invariant["second_episode_under_v1_allowed"] is False
    assert invariant["rescue_rerun_allowed"] is False
    assert invariant["return_to_armed_allowed"] is False
    assert invariant["return_to_preregistered_not_executed_allowed"] is False
    assert invariant["return_to_authorized_unconsumed_allowed"] is False


def test_execution_and_scientific_state_cannot_be_rewritten_as_a_scientific_failure():
    record = load(RESULT)
    execution = record["execution"]
    science = record["scientific_interpretation"]
    assert execution["execution_verdict"] == "EXECUTION_FAIL_CLOSED"
    assert execution["terminal_reason"] == "UNRESOLVED_CRITICAL_HIGH_AFTER_SINGLE_TARGETED_REREVIEW"
    assert execution["native_baseline_dispatched"] is False
    assert execution["verifier_dispatched"] is False
    assert execution["scorer_released"] is False
    assert execution["answer_key_released"] is False
    assert science["scientific_comparison_completed"] is False
    assert science["stage_a_v1_scientific_comparison_result"] == "NOT_OBTAINED"
    assert science["not_stage_a_v1_fail"] is True


def test_attribution_separates_proven_plumbing_from_unresolved_write_cause():
    record = load(RESULT)
    attribution = load(ATTRIBUTION)
    assert record["attribution"]["proven_result_status_propagation_defect"] is True
    assert record["attribution"]["proven_execution_test_stage_deficiency"] is True
    assert record["attribution"]["write_capability_failure_observed"] is True
    assert record["attribution"]["write_capability_root_cause"] == "UNRESOLVED"
    assert record["attribution"]["dsh_causality_proven"] is False
    assert attribution["causal_attribution_to_dsh"] == "INSUFFICIENT_EVIDENCE"
    assert all(item["causal_scope"] == "EXECUTION_PLUMBING_ONLY" for item in attribution["proven_episode_execution_defects"])
    assert attribution["unresolved_treatment_observation"]["dsh_causality_proven"] is False


def test_no_native_comparison_or_dsh_win_loss_claim_is_recorded():
    record = load(RESULT)
    science = record["scientific_interpretation"]
    assert science["dsh_vs_native_comparison_completed"] is False
    assert science["dsh_worse_than_native_established"] is False
    assert science["dsh_better_than_native_established"] is False
    assert science["native_better_than_dsh_established"] is False
    assert science["dsh_noninferiority_established"] is False


def test_v2_is_pending_qualification_without_authority():
    record = load(RESULT)
    assert record["v2"]["status"] == "NOT_YET_JUSTIFIED_PENDING_NONEXPERIMENTAL_EXECUTION_PLUMBING_QUALIFICATION"
    assert len(record["v2"]["prerequisites_recorded"]) == 8
    assert record["authority"] == {
        "runtime_authority": "NONE",
        "scientific_authority": "NONE",
        "qnty_next_action": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
    }


def test_evidence_manifest_binds_sanitized_preserved_artifacts():
    manifest = load(EVIDENCE)
    assert manifest["episode_id"] == "SUBSCRIPTION_BACKED_STAGE_A_V1-1787094263"
    assert manifest["answer_key_material_accessed"] is False
    assert manifest["sealed_answer_references_required"] is False
    paths = {item["path"] for item in manifest["artifacts"]}
    required = {
        "execution_summary.md",
        "evidence_hashes.json",
        "driver_manifest.json",
        "episode_manifest.json",
        "diagnostics.json",
        "receipts/treatment_receipt.json",
        "receipts/baseline_receipt.json",
        "scorer_result.json",
        "logs/dsh_treatment_builder_initial_0.json",
        "logs/dsh_treatment_builder_repair_0.json",
        "logs/dsh_treatment_hostile_reviewer_initial_0.json",
        "logs/dsh_treatment_hostile_reviewer_targeted_rereview_0.json",
    }
    assert required <= paths
    for item in manifest["artifacts"]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        assert "/" not in item["sha256"]


def test_answer_key_references_are_not_required_or_recorded():
    text = "\n".join(path.read_text(encoding="utf-8") for path in (RESULT, ATTRIBUTION, EVIDENCE, REVIEW))
    assert all(reference not in text for reference in SEALED_REFERENCES)
    assert load(RESULT)["answer_key_accessed"] is False


def test_project_state_records_consumed_fail_closed_episode_without_authority():
    registry = PROJECTS.read_text(encoding="utf-8")
    assert 'project_id = "SUBSCRIPTION_BACKED_STAGE_A_V1_RESULT_RECORDING_V0"' in registry
    assert 'execution_verdict = "EXECUTION_FAIL_CLOSED"' in registry
    assert "episode_consumed = true" in registry
    assert "scientific_comparison_completed = false" in registry
    assert "native_baseline_dispatched = false" in registry
    assert "scorer_released = false" in registry
    assert "answer_key_released = false" in registry
    assert "result_recorded = true" in registry
    assert "second_episode_allowed = false" in registry
    assert "rescue_rerun_allowed = false" in registry
    assert 'dsh_causality_proven = false' in registry
    assert 'execution_plumbing_defect_proven = true' in registry
    assert 'v2_status = "NOT_YET_JUSTIFIED_PENDING_NONEXPERIMENTAL_EXECUTION_PLUMBING_QUALIFICATION"' in registry
    assert 'qnty_next_action_authority = "NONE"' in registry
    assert 'trading_authority = "NONE"' in registry
    assert 'capital_authority = "NONE"' in registry


def test_evidence_hashes_are_sha256_identifiers_not_credentials():
    manifest = load(EVIDENCE)
    assert all(len(item["sha256"]) == hashlib.sha256().digest_size * 2 for item in manifest["artifacts"])
    assert "api_key" not in EVIDENCE.read_text(encoding="utf-8").lower()
