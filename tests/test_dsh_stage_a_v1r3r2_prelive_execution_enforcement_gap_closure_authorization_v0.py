from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_authorization_v0"
)
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_AUTHORIZATION_V0"
IMPLEMENTATION_ID = "DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_V0"
V0R1_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_unique_authorization_identity_and_exact_future_phase() -> None:
    assert AUTH["project_id"] == AUTHORIZATION_ID
    assert AUTH["future_implementation_project_id"] == IMPLEMENTATION_ID
    assert AUTHORIZATION_ID != IMPLEMENTATION_ID
    assert AUTH["authorized_operation"] == "EXACTLY_ONE_OFFLINE_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_PHASE"
    assert AUTH["canonicalization"]["duplicate_authorization_allowed"] is False


def test_canonical_only_effectiveness_and_exact_predecessor() -> None:
    canonical = AUTH["canonicalization"]
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert canonical["candidate_base_sha"] == "276c1706c02bdb4fcc0d3e688c371e20fcee2065"
    assert canonical["branch_local_artifact_does_not_self_authorize"] is True
    assert canonical["canonical_presence_required_before_implementation"] is True
    assert AUTH["future_implementation_authority_after_construction"]["available_on_branch"] is False
    assert AUTH["canonical_predecessor"] == {
        "project_id": V0R1_EXECUTION_ID,
        "pr": 188,
        "reviewed_head": "6c3434ac02051e1f9d3a3baa02a6103e2693a406",
        "merge": "276c1706c02bdb4fcc0d3e688c371e20fcee2065",
        "required_state": "CLOSED_BLOCKED",
        "episode_claimed": False,
        "episode_consumed": False,
        "binding_mismatch_behavior": "BLOCK_AUTH",
    }


def test_pr189_and_v0r1_cannot_substitute() -> None:
    held = AUTH["held_pr_189"]
    assert held["number"] == 189
    assert held["head"] == "aa6b383c41a68e52f35c3c0e1fcae61e7cf0004d"
    assert held["canonical"] is False and held["merged"] is False
    assert held["modified_by_this_phase"] is False
    assert held["substitutes_for_this_authorization"] is False
    assert held["authorizes_future_implementation"] is False
    assert AUTH["canonical_predecessor"]["project_id"] == V0R1_EXECUTION_ID
    assert AUTH["canonical_predecessor"]["required_state"] == "CLOSED_BLOCKED"
    rejected = AUTH["historical_authority_rejected"]
    assert rejected["v0r1_authorization_project_id"] == (
        "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1"
    )
    assert rejected["v0r1_execution_project_id"] == V0R1_EXECUTION_ID
    assert rejected["v0r1_authorization_or_activation_substitution_allowed"] is False
    assert rejected["held_pr_189_project_id"] == (
        "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2"
    )
    assert rejected["held_pr_189_substitution_allowed"] is False
    assert rejected["only_this_exact_authorization_may_authorize_future_implementation_after_canonical_merge"] is True


def test_triggering_evidence_is_exact_and_non_speculative() -> None:
    evidence = AUTH["triggering_evidence"]
    assert evidence["classification"] == "CONCRETE_PRELIVE_FALSIFYING_FINDINGS_NOT_SPECULATIVE_CLEANUP"
    historical = evidence["historical_stage_a"]
    assert _sha256(historical["artifact"]) == historical["sha256"]
    assert historical["codex_tool_calls_observed"] == 3
    assert historical["intended_codex_max"] == 2
    gate = evidence["qualified_budget_gate"]
    assert _sha256(gate["v1r3r2_reexport_artifact"]) == gate["v1r3r2_reexport_sha256"]
    assert _sha256(gate["implementation_artifact"]) == gate["implementation_sha256"]
    assert gate["parent_request_ceiling"] == 8
    assert gate["workflow_state_machine"] is False
    qualification = evidence["v1r3r2_qualification"]
    assert _sha256(qualification["artifact"]) == qualification["sha256"]
    assert qualification["codex_actual_task_calls"] == 0
    assert qualification["claude_actual_task_calls"] == 0
    assert qualification["failing_child_sequence_empirically_proven"] is False


def test_offline_runtime_modification_scope_is_bounded() -> None:
    scope = AUTH["future_authority_scope"]
    assert scope["smallest_necessary_runtime_or_policy_repair_authorized"] is True
    assert scope["historical_evidence_mutation_authorized"] is False
    assert scope["real_episode_artifact_mutation_authorized"] is False
    assert "bounded claim helper code" in scope["modify_if_necessary"]
    assert "qualification artifacts only if covered runtime or policy identity changes" in scope["create"]


def test_child_state_machine_acceptance_is_exact_and_predispatch() -> None:
    child = AUTH["required_child_state_machine"]
    assert child["pre_dispatch_enforcement_required"] is True
    assert child["codex_calls_max"] == 2 and child["claude_calls_max"] == 2
    assert child["invalid_transition_denied_before_native_child_spawn"] is True
    assert child["transitions"] == [
        "INITIAL -> exactly one Codex implementation",
        "AFTER_INITIAL_CODEX -> exactly one Claude hostile review",
        "AFTER_REVIEW_NO_CRITICAL_HIGH -> TERMINAL",
        "AFTER_REVIEW_CRITICAL_HIGH -> exactly one Codex repair",
        "AFTER_REPAIR -> exactly one Claude targeted rereview",
        "AFTER_REREVIEW -> TERMINAL",
    ]
    assert set(child["must_reject"]) == {
        "third Codex",
        "third Claude",
        "duplicate initial Codex",
        "Claude before initial Codex completion",
        "repair without Critical or High",
        "second repair",
        "rereview without repair",
        "generic child route",
        "alternative child provider",
        "background delegation",
    }


def test_parent_budget_and_claim_acceptance_fail_closed() -> None:
    parent = AUTH["required_parent_budget"]
    assert parent["max_parent_request_attempts"] == 8
    assert parent["attempt_9_denied_before_adapter_or_provider_io"] is True
    assert parent["max_tokens_per_request"] == 4096
    assert parent["max_total_authorized_spend_usd"] == 1.0
    assert parent["reservation_before_every_paid_dispatch_required"] is True
    assert parent["automatic_provider_retries"] is False
    assert parent["auxiliary_model_route_bypass"] is False
    claim = AUTH["required_claim_acceptance"]
    assert claim["fixtures"] == "DISPOSABLE_FILESYSTEM_AND_BARE_GIT_ONLY"
    assert len(claim["cases"]) == 8
    assert claim["partial_or_ambiguous_state_makes_second_episode_eligible"] is False
    assert claim["at_most_once_priority"] == "SAFETY_OVER_AVAILABILITY"
    assert claim["real_v0r2_claim_authorized"] is False


def test_secret_firewall_and_live_equivalent_offline_harness_are_required() -> None:
    secret = AUTH["required_secret_firewall"]
    assert secret["credential_kind"] == "FAKE_SENTINEL_ONLY"
    assert secret["sentinel_reaches_parent_through_exact_extra_env_seam"] is True
    assert secret["sentinel_reaches_codex"] is False
    assert secret["sentinel_reaches_claude"] is False
    assert secret["sentinel_reaches_persisted_state_logs_receipts_or_evidence"] is False
    assert secret["sentinel_hash_or_serialization_allowed"] is False
    integration = AUTH["required_offline_integration"]
    assert integration["profile"] == "FULL_PROFILE_LIVE_EQUIVALENT_OFFLINE"
    assert integration["mock_parent_attempts_forbidden_sequences"] is True
    assert integration["enforcement_layer_must_block_forbidden_sequences"] is True
    assert integration["cooperative_mock_parent_is_decisive_proof"] is False
    assert integration["synthetic_helper_only_tests_are_decisive_proof"] is False
    assert integration["external_network_authorized"] is False


def test_requalification_is_conditional_on_covered_identity_change() -> None:
    consequence = AUTH["qualification_consequence"]
    assert consequence["historical_qualified_launch_contract_digest"] == (
        "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
    )
    assert consequence["historical_evidence_preserved"] is True
    assert consequence["covered_identity_change_makes_old_contract_valid_for_new_runtime"] is False
    assert consequence["conditional_requalification_authorized"] is True
    assert consequence["requalification_max"] == 1
    assert consequence["requalification_only_if_covered_identity_changes"] is True
    assert consequence["unchanged_components_requalified_without_need"] is False
    assert consequence["requalification_live_episode_authorized"] is False
    assert AUTH["pr_189_consequence"]["if_runtime_or_policy_identity_changes"] == "SUPERSEDED_NOT_MERGEABLE"


def test_no_live_or_downstream_authority_and_zero_construction_side_effects() -> None:
    boundary = AUTH["governance_boundary"]
    denied = (
        "live_execution_authorized",
        "activation_authorized",
        "real_secret_read_authorized",
        "real_claim_authorized",
        "real_provider_io_authorized",
        "live_dsh_codex_or_claude_authorized",
        "stage_b_authorized",
        "scientific_execution_or_promotion_authorized",
        "production_deployment_authorized",
    )
    assert all(boundary[key] is False for key in denied)
    assert boundary["spend_authorized_usd"] == 0.0
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"
    receipts = AUTH["construction_receipts"]
    assert all(
        receipts[key] == 0
        for key in (
            "runtime_files_modified",
            "qualification_runs",
            "activation_artifacts_created",
            "real_secret_reads",
            "real_claims_created",
            "provider_or_model_requests",
            "live_dsh_codex_or_claude_invocations",
        )
    )
    assert receipts["spend_usd"] == 0.0
    assert receipts["pr_189_modified"] is False


def test_closed_registry_and_generated_views_are_consistent() -> None:
    assert AUTH["phase_state"] == "CLOSED_PASS"
    assert AUTH["review_policy"]["hostile_review_count_actual"] == 1
    assert AUTH["review_policy"]["hostile_review_verdict"] == "PASS"
    assert AUTH["construction_receipts"]["hostile_review_completed"] is True
    assert (ARTIFACT / "hostile_governance_review.md").is_file()
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    record = projects[AUTHORIZATION_ID]
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert record["state"] == "CLOSED_PASS"
    assert record["implementation_authorized"] is False
    assert record["future_implementation_project_id"] == IMPLEMENTATION_ID
    assert record["future_implementation_authorized_after_canonicalization"] is True
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert subprocess.run(
        ["python", "-m", "qntylab.project_context", "render", "--check"],
        cwd=ROOT,
        check=False,
    ).returncode == 0
