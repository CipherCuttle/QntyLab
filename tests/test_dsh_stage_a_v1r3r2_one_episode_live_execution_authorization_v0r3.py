from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r3"
)
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
CONTRACT_PATH = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_launch_contract_requalification_v0/evidence/contract.json"
)
QUALIFICATION_PATH = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_launch_contract_requalification_v0/qualification.json"
)
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R3"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r3"
E168 = "e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82"
E3B = "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa"
C98 = "c98c0a91d15c0875e3635e9791561af5bbb8588ff66d4144c822570b6227b666"


def test_exact_e168_contract_and_artifact_identity_are_bound() -> None:
    qualified = AUTH["qualified_launch_contract"]
    assert qualified["digest"] == E168 == CONTRACT["qualifiedContractDigest"]
    assert qualified["launch_policy_digest"] == CONTRACT["digests"]["LAUNCH_POLICY_DIGEST"]
    assert qualified["runtime_manifest_digest"] == CONTRACT["digests"]["RUNTIME_MANIFEST_DIGEST"]
    assert qualified["executable_identity_digest"] == CONTRACT["digests"]["EXECUTABLE_IDENTITY_DIGEST"]
    assert qualified["contract_artifact_sha256"] == hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert qualified["qualification_artifact_sha256"] == hashlib.sha256(QUALIFICATION_PATH.read_bytes()).hexdigest()


def test_predecessor_contracts_are_rejected_as_current() -> None:
    rejected = AUTH["qualified_launch_contract"]["superseded_digests_rejected"]
    assert E3B in rejected
    assert C98 in rejected
    assert "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1" in rejected
    assert E168 not in rejected
    assert AUTH["qualified_launch_contract"]["mismatch_behavior"].startswith("BLOCK_BEFORE_SECRET_READ")


def test_prior_authorization_activation_episode_and_claim_lineages_cannot_substitute() -> None:
    history = AUTH["historical_authority_rejected"]
    for suffix in ("V0", "V0R1", "V0R2", "V0R2R1"):
        assert f"DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_{suffix}" in history["authorization_project_ids"]
        assert f"DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_{suffix}" in history["activation_project_ids"]
        assert f"DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_{suffix}#EPISODE_1" in history["episode_ids"]
    assert "V0R3" not in " ".join(history["authorization_project_ids"])
    assert AUTH["claim_contract"]["historical_claim_refs_rejected"][-1].endswith("v0r2r1")
    assert AUTH["superseded_pr_189"]["authorization_substitution_allowed"] is False


def test_fresh_identity_tuple_is_exactly_one_and_collision_free() -> None:
    assert AUTH["project_id"] == AUTHORIZATION_ID
    assert AUTH["fresh_identity"]["future_activation_project_id"] == EXECUTION_ID
    assert AUTH["fresh_identity"]["episode_id"] == EPISODE_ID
    assert AUTH["fresh_identity"]["claim_remote_ref"] == CLAIM_REF
    assert AUTH["episode_authority"]["episode_count"] == 1
    assert AUTH["episode_authority"]["live_episodes_max"] == 1
    assert AUTH["episode_authority"]["second_episode_allowed"] is False
    assert AUTH["fresh_identity"]["collision_free_successor"] is True


def test_previous_attempt_remains_unclaimed_and_unconsumed_without_reuse() -> None:
    state = AUTH["historical_episode_states"][
        "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1#EPISODE_1"
    ]
    assert state["claimed"] is False
    assert state["consumed"] is False
    assert state["reused_by_this_phase"] is False
    assert state["new_authority_required"] is True


def test_authorization_phase_has_zero_secret_claim_provider_model_child_and_spend_activity() -> None:
    assert AUTH["construction_receipts"] == {
        "real_secret_reads": 0,
        "claims_created": 0,
        "live_dsh_calls": 0,
        "external_provider_requests": 0,
        "real_model_calls": 0,
        "codex_child_turns": 0,
        "claude_child_turns": 0,
        "fixture_mutations": 0,
        "activation_artifacts_created": 0,
        "spend_usd": "0",
    }


def test_parent_model_route_budget_retry_and_spend_policy_are_frozen() -> None:
    parent = AUTH["parent_authority"]
    assert (parent["provider"], parent["model"], parent["route"]) == ("openai", "gpt-5-mini", "llm-pi-ai")
    assert parent["max_request_attempts"] == 8
    assert parent["provider_internal_retries"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["max_output_tokens_per_request"] == 4096
    assert parent["alternate_provider_allowed"] is False
    assert parent["model_substitution_allowed"] is False
    assert AUTH["spend_authority"]["cap_usd"] == "1.00"
    assert AUTH["spend_authority"]["hard_cap"] is True
    assert AUTH["spend_authority"]["price_schedule_id"] == "openai-gpt-5-mini-2026-08-22-4x-authorization-reserve-v0"


def test_child_limits_and_sequence_are_hard_frozen() -> None:
    child = AUTH["child_authority"]
    assert child["codex_calls_max"] == 2
    assert child["claude_calls_max"] == 2
    assert child["reservation_before_native_spawn"] is True
    assert child["invalid_transition_denied_before_native_spawn"] is True
    assert child["generic_child_tools"] == []
    assert child["alternate_delegation_routes"] == []
    assert child["background_delegation"] is False


def test_claude_is_hard_read_only_with_exact_surface() -> None:
    claude = AUTH["child_execution_policies"]["claude"]
    assert claude["read_only"] is True
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert claude["disallowed_tools"] == ["Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"]
    assert claude["permission_mode"] == "dontAsk"
    assert claude["setting_sources"] == []
    assert claude["strict_mcp_config"] is True
    assert claude["mcp_servers"] == {}
    assert claude["agents"] == {}
    assert claude["plugins"] == []
    assert claude["persistence"] is False


def test_secret_gate_is_after_non_secret_gates_and_before_claim() -> None:
    order = AUTH["action_time_gate_order"]
    secret = order.index("verify secret file availability/readability/nonempty")
    read = order.index("read secret into memory only and bind OPENAI_API_KEY through explicit extraEnv")
    claim = order.index("create fresh durable at-most-once claim")
    provider = order.index("allow DSH/provider I/O only after successful claim")
    assert secret > order.index("verify parent/child budgets and Stage-B/Qnty/scientific/trading/capital firewall")
    assert secret < read < claim < provider
    assert AUTH["secret_binding_contract"]["source_path"] == "~/.secrets/openai_api_key_stage_a"
    assert AUTH["secret_binding_contract"]["auth_env"] == "OPENAI_API_KEY"
    assert AUTH["secret_binding_contract"]["authorization_phase_secret_reads"] == 0


def test_claim_is_create_only_at_most_once_and_binds_fresh_tuple() -> None:
    claim = AUTH["claim_contract"]
    assert claim["mode"] == "CREATE_ONLY_AT_MOST_ONCE_NO_OVERWRITE_NO_REPLAY_NO_REUSE"
    assert claim["remote_claim_create_only_fail_if_exists"] is True
    assert claim["force_update_forbidden"] is True
    assert claim["claim_deletion_or_reset_forbidden"] is True
    assert claim["created_during_authorization_construction"] is False
    assert claim["future_execution_tuple"] == {
        "authorization_project_id": AUTHORIZATION_ID,
        "activation_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "qualified_contract_digest": E168,
        "canonical_master": "52ae5fe3a7df10a7b35d04789d6c0ce509e74b04",
    }


def test_timeout_and_terminal_failure_never_authorize_rerun() -> None:
    timeout = AUTH["timeout_policy"]
    assert timeout["live_episode_timeout_seconds"] == 1800
    assert timeout["timeout_allows_rerun"] is False
    assert timeout["terminal_failure_allows_rerun"] is False
    assert timeout["second_episode_or_rescue_allowed"] is False
    assert timeout["new_authority_required_after_closure"] is True


def test_runtime_binding_preserves_physical_and_live_profiles_and_exact_identities() -> None:
    runtime = AUTH["runtime_binding"]
    assert runtime["physical_profile"] == "headless"
    assert runtime["stage_a_live_profile"] == "PRODUCTION"
    assert runtime["source_identity"] == {
        "remote": "https://github.com/deepseek-ai/deepseek-harness.git",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
    }
    assert runtime["toolchain"]["lockfile_digest"] == "f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea"
    assert runtime["launch_policy_digest"] == "00336402a7b34757ba05194ae083805b84f699f1f706990278b9aaf121e973b4"
    assert runtime["no_runtime_rebuild_or_byte_modification_in_authorization"] is True


def test_authorization_and_activation_are_distinct_and_branch_local_is_ineffective() -> None:
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert AUTH["canonicalization"]["candidate_base_sha"] == "52ae5fe3a7df10a7b35d04789d6c0ce509e74b04"
    assert AUTH["canonicalization"]["branch_local_artifact_does_not_self_authorize"] is True
    assert AUTH["canonicalization"]["authorization_does_not_activate"] is True
    assert AUTH["activation_prerequisite"]["activation_creation_during_this_phase"] is False
    assert not list(ARTIFACT.glob("activation.json"))
    assert AUTH["execution_authority_after_construction"]["effective_execution_authority"] is False


def test_authority_firewall_denies_execution_and_all_downstream_authority() -> None:
    firewall = AUTH["authority_firewall"]
    assert firewall["live_execution_authorized_this_phase"] is False
    assert firewall["activation_created_this_phase"] is False
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
    assert firewall["broader_production_authority"] == "NONE"


def test_project_context_projection_remains_fail_closed_and_inactive() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    record = projects[AUTHORIZATION_ID]
    assert record["state"] == "CLOSED_PASS"
    assert record["activation_exists"] is False
    assert record["effective_execution_authority"] is False
    assert projection["active_project"] is None
    assert projection["issues"] == []


def test_registry_and_next_action_describe_only_future_separate_activation() -> None:
    assert AUTH["terminal_verdict"] == "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_AUTHORIZATION_READY"
    assert "separate activation phase" in AUTH["next_action"]
    assert "do not activate or execute" in AUTH["next_action"]
    assert AUTH["superseded_pr_189"]["status"] == "SUPERSEDED_NOT_MERGEABLE"
