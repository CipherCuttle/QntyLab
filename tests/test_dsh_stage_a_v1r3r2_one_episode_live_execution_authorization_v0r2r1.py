from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r2r1"
)
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2R1"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = (
    "refs/heads/qntylab-claims/"
    "dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2r1"
)
OLD_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2"
OLD_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2"
OLD_CLAIM_REF = (
    "refs/heads/qntylab-claims/"
    "dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2"
)
OLD_DIGEST = "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
NEW_DIGEST = "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa"


def test_case_01_pr189_authorization_cannot_satisfy_v0r2r1() -> None:
    assert AUTH["project_id"] == AUTHORIZATION_ID
    assert AUTHORIZATION_ID != OLD_AUTHORIZATION_ID
    rejected = AUTH["historical_authority_rejected"]
    assert OLD_AUTHORIZATION_ID in rejected["authorization_project_ids"]
    assert rejected["substitution_allowed"] is False
    assert AUTH["superseded_pr_189"]["authorization_substitution_allowed"] is False


def test_case_02_pr189_execution_identity_cannot_satisfy_v0r2r1() -> None:
    assert AUTH["execution_project_id"] == EXECUTION_ID
    assert EXECUTION_ID != OLD_EXECUTION_ID
    assert OLD_EXECUTION_ID in AUTH["historical_authority_rejected"]["execution_project_ids"]
    assert AUTH["activation_prerequisite"]["old_authorization_or_activation_satisfies"] is False


def test_case_03_pr189_claim_ref_cannot_substitute() -> None:
    claim = AUTH["claim_contract"]
    assert claim["remote_claim_ref"] == CLAIM_REF
    assert CLAIM_REF != OLD_CLAIM_REF
    assert OLD_CLAIM_REF in claim["historical_claim_refs_rejected"]
    assert AUTH["superseded_pr_189"]["claim_substitution_allowed"] is False


def test_case_04_old_qualified_digest_fails_closed() -> None:
    contract = AUTH["qualified_launch_contract"]
    assert contract["old_digest"] == OLD_DIGEST
    assert contract["old_digest_still_valid"] is False
    assert OLD_DIGEST in AUTH["historical_authority_rejected"][
        "qualified_launch_contract_digests"
    ]
    assert contract["mismatch_behavior"] == (
        "BLOCK_BEFORE_SECRET_READ_CHILD_SPAWN_AND_PROVIDER_IO"
    )


def test_case_05_replacement_contract_and_canonical_enforcement_bytes_are_required() -> None:
    contract = AUTH["qualified_launch_contract"]
    assert contract["digest"] == NEW_DIGEST
    assert contract["runtime_manifest_digest"] == (
        "afcfa011de46bd9fccaa120b5612c24a5ace2b2c451591ddf8b67fb43a8ce321"
    )
    assert contract["executable_identity_digest"] == (
        "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
    )
    assert contract["launch_policy_digest"] == (
        "024256a6dd2fbce6e883a73d9d2df01e3b2b21f738c7ca700c86cca13bd1ec73"
    )
    for relative, expected in AUTH["canonical_enforcement_bytes"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_case_06_authorization_alone_does_not_activate() -> None:
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert AUTH["activation_prerequisite"]["activation_exists_initial"] is False
    assert AUTH["activation_prerequisite"]["activation_creation_during_this_phase"] is False
    assert AUTH["execution_authority_after_construction"]["effective_execution_authority"] is False
    assert not list(ARTIFACT.glob("activation.json"))


def test_case_07_noncanonical_authorization_is_ineffective() -> None:
    canonical = AUTH["canonicalization"]
    assert canonical["candidate_base_sha"] == "6221972c69c7dd8c177f856de261beffbfaf90c0"
    assert canonical["branch_local_artifact_does_not_self_authorize"] is True
    assert canonical["canonical_presence_required_before_execution"] is True

    def effective(*, on_canonical_master: bool, activation_exists: bool) -> bool:
        return on_canonical_master and activation_exists

    assert effective(on_canonical_master=False, activation_exists=True) is False
    assert effective(on_canonical_master=True, activation_exists=False) is False


def test_case_08_claim_remote_ref_local_tuple_is_exact_and_not_caller_selectable() -> None:
    claim = AUTH["claim_contract"]
    assert claim["remote"] == "https://github.com/CipherCuttle/QntyLab.git"
    assert claim["remote_claim_ref"] == CLAIM_REF
    assert claim["claim_project_id"] == EXECUTION_ID
    assert claim["episode_id"] == EPISODE_ID
    assert claim["authorization_id"] == AUTHORIZATION_ID
    assert claim["local_receipt_namespace"] == "/var/tmp/qntylab-claims"
    assert claim["state_dir"] == (
        "/var/tmp/qntylab-claims/"
        "dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2r1/episode-1"
    )
    assert claim["helper_path_derivation"] == {
        "lock": "state_dir / 'claim.lock'",
        "intent": "state_dir / 'claim-intent.json'",
        "receipt": "state_dir / 'claim-receipt.json'",
    }
    assert claim["remote_caller_selectable"] is False
    assert claim["claim_ref_caller_selectable"] is False
    assert claim["local_receipt_namespace_caller_selectable"] is False
    assert claim["semantic_ids_caller_selectable"] is False
    assert claim["partial_claim_behavior"] == "BLOCK_NEVER_REPLAY"
    assert claim["claim_deletion_or_reset_forbidden"] is True


def test_case_09_child_sequence_and_maxima_bind_repaired_gate() -> None:
    child = AUTH["child_authority"]
    assert child["enforcement_module"].endswith(".StageAChildController")
    assert child["reservation_before_native_spawn"] is True
    assert child["invalid_transition_denied_before_native_spawn"] is True
    assert child["codex_calls_max"] == 2
    assert child["claude_calls_max"] == 2
    assert child["state_machine"] == [
        "INITIAL -> INITIAL_CODEX_RUNNING -> AFTER_INITIAL_CODEX",
        "AFTER_INITIAL_CODEX -> CLAUDE_REVIEW_RUNNING -> AFTER_REVIEW_NO_C_H (TERMINAL)",
        "AFTER_INITIAL_CODEX -> CLAUDE_REVIEW_RUNNING -> AFTER_REVIEW_C_H",
        "AFTER_REVIEW_C_H -> CODEX_REPAIR_RUNNING -> AFTER_REPAIR",
        "AFTER_REPAIR -> CLAUDE_REREVIEW_RUNNING -> AFTER_REREVIEW (TERMINAL)",
    ]


def test_case_10_parent_request_ceiling_binds_repaired_gate() -> None:
    parent = AUTH["parent_authority"]
    assert parent["enforcement_module"].endswith(".ParentBudgetGate")
    assert (parent["provider"], parent["model"], parent["route"]) == (
        "openai",
        "gpt-5-mini",
        "llm-pi-ai",
    )
    assert parent["max_request_attempts"] == 8
    assert parent["attempt_9"] == "DENY_BEFORE_PROVIDER_WIRE_IO"
    assert parent["provider_internal_retries"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["hidden_retry_bypass"] is False
    assert parent["actual_wire_attempts_bound"] == (
        "EQUALS_RESERVED_LOGICAL_ATTEMPTS_AND_AT_MOST_8"
    )


def test_case_11_request_level_4096_output_token_cap_is_bound() -> None:
    parent = AUTH["parent_authority"]
    assert parent["max_output_tokens_per_request"] == 4096
    assert parent["oversize_output_request"] == "REJECT_BEFORE_PROVIDER_DISPATCH"


def test_case_12_spend_scope_is_parent_openai_authorized_spend_only() -> None:
    spend = AUTH["spend_authority"]
    assert spend["scope"] == "PARENT_OPENAI_AUTHORIZED_SPEND_USD_UNDER_FROZEN_SCHEDULE"
    assert spend["cap_usd"] == "1.00"
    assert spend["price_schedule_id"] == (
        "openai-gpt-5-mini-2026-08-22-4x-authorization-reserve-v0"
    )
    assert spend["input_token_cost_included"] is True
    assert spend["maximum_permitted_output_token_cost_included"] is True
    assert spend["reservation_before_potentially_paid_dispatch"] is True
    assert spend["total_all_model_cash_spend_claimed"] is False


def test_case_13_explicit_extra_env_secret_binding_is_required() -> None:
    secret = AUTH["secret_binding_contract"]
    assert secret["auth_env"] == "OPENAI_API_KEY"
    assert secret["source_path"] == "~/.secrets/openai_api_key_stage_a"
    assert secret["explicit_extra_env_required"] is True
    assert secret["ambient_process_inheritance_relied_on"] is False
    assert secret["binding_mechanism"] == (
        "spawnDsh(..., { extraEnv: { OPENAI_API_KEY: value } })"
    )
    assert AUTH["action_time_order"].index("create durable at-most-once claim") < (
        AUTH["action_time_order"].index("allow provider I/O only after successful claim")
    )


def test_case_14_child_secret_firewall_and_claude_read_only_are_bound() -> None:
    secret = AUTH["secret_binding_contract"]
    claude = AUTH["child_execution_policies"]["claude"]
    assert secret["sentinel_firewall_binding"] == "PASS_ZERO_CHILD_OR_PERSISTED_LEAKS"
    assert secret["exposed_to_codex"] is False
    assert secret["exposed_to_claude"] is False
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert claude["disallowed_tools"] == [
        "Write",
        "Edit",
        "Bash",
        "Agent",
        "Task",
        "mcp__*",
        "AskUserQuestion",
        "delegation",
    ]
    assert claude["permission_mode"] == "dontAsk"
    assert claude["setting_sources"] == []
    assert claude["strict_mcp_config"] is True
    assert claude["mcp_servers"] == {}
    assert claude["agents"] == {}
    assert claude["plugins"] == []
    assert claude["persistence"] is False


def test_case_15_arbitrary_offline_patch_cannot_satisfy_production_execution() -> None:
    profile = AUTH["profile_contract"]
    assert profile["live_profile"] == "PRODUCTION"
    assert profile["production_policy_patch"].endswith("/profile/cordis.patch.yml")
    assert profile["offline_qualification_patch"].endswith("/stub/offline-stub.patch.yml")
    assert profile["offline_qualification_patch_allowed_for_live"] is False
    assert profile["arbitrary_patch_allowed"] is False
    assert profile["action_time_profile_or_patch_override_allowed"] is False
    assert profile["qualification_only_bytes_are_evidence_not_live_inputs"] is True


def test_case_16_provider_io_before_successful_claim_is_forbidden() -> None:
    claim = AUTH["claim_contract"]
    assert AUTH["provider_io_before_claim_forbidden"] is True
    assert claim["both_complete_before_first_potentially_paid_parent_dispatch"] is True
    assert AUTH["action_time_order"][-2:] == [
        "create durable at-most-once claim",
        "allow provider I/O only after successful claim",
    ]


def test_case_17_second_episode_and_whole_episode_retry_are_forbidden() -> None:
    episode = AUTH["episode_authority"]
    assert episode["episode_id"] == EPISODE_ID
    assert episode["live_episodes_max"] == 1
    assert episode["second_episode_allowed"] is False
    assert episode["whole_episode_retry_allowed"] is False
    assert episode["timeout_seconds"] == 1800
    assert episode["claim_crossed_timeout_or_crash_behavior"] == "BLOCK_NEVER_REPLAY"
    assert AUTH["execution_closure_pr_budget"] == 1


def test_case_18_stage_b_qnty_trading_capital_and_science_are_denied() -> None:
    firewall = AUTH["governance_boundary"]
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["production_deployment_authority"] == (
        "NONE_OUTSIDE_THIS_STAGE_A_EXPERIMENT"
    )
    assert firewall["future_stage_a_pass_establishes_trading_edge"] is False
    assert firewall["future_stage_a_pass_establishes_scientific_utility"] is False


def test_raw_sanitized_receipts_fixture_and_workspace_contracts_are_complete() -> None:
    evidence = AUTH["raw_sanitized_execution_evidence_required"]
    negative_fields = {"curated_summary_alone_sufficient", "secret_content_allowed"}
    assert all(value is True for key, value in evidence.items() if key not in negative_fields)
    assert evidence["curated_summary_alone_sufficient"] is False
    assert evidence["secret_content_allowed"] is False
    fixture = AUTH["fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["fixture_digest"] == (
        "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"
    )
    assert fixture["mutable_paths_in_disposable_copy"] == ["retry.py"]
    assert fixture["immutable_paths"] == ["TASK.md", "tests/test_retry.py"]
    workspace = AUTH["workspace_policy"]
    assert workspace["fresh_disposable_workspace_required"] is True
    assert workspace["fresh_disposable_dsh_home_required"] is True
    assert workspace["realpath_symlink_aware_containment_required"] is True


def test_construction_is_zero_live_activity_and_project_context_has_no_active_project() -> None:
    assert AUTH["construction_receipts"] == {
        "real_secret_reads": 0,
        "claim_creations": 0,
        "live_dsh_calls": 0,
        "external_provider_requests": 0,
        "real_codex_child_turns": 0,
        "real_claude_child_turns": 0,
        "spend_usd": "0",
        "fixture_mutations": 0,
        "activation_artifacts_created": 0,
    }
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projects[AUTHORIZATION_ID]["state"] == "CLOSED_PASS"
    assert projects[AUTHORIZATION_ID]["activation_exists"] is False
    assert projects[AUTHORIZATION_ID]["effective_execution_authority"] is False
    assert projection["issues"] == []
    assert projection["active_project"] is None
