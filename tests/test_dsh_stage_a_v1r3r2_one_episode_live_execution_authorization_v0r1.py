from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r1"
)
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
QUALIFICATION = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/qualification.json"
)
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"
OLD_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0"
OLD_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0"


def test_fresh_lineage_binds_repaired_canonical_projection_and_exact_runtime() -> None:
    assert AUTH["project_id"] == AUTHORIZATION_ID
    assert AUTH["execution_project_id"] == EXECUTION_ID
    assert AUTH["project_id"] != OLD_AUTHORIZATION_ID
    assert AUTH["execution_project_id"] != OLD_EXECUTION_ID
    assert AUTH["canonicalization"]["candidate_base_sha"] == "e74c50970bbe1caa780cc85eb40f4b5c62f3b444"
    assert AUTH["canonical_predecessor"] == {
        "project_id": "DSH_STAGE_A_CANONICAL_ACTIVATION_PROJECTION_INTEGRITY_V0",
        "pr": 185,
        "reviewed_head": "8cbe18ca816e542e9612c9dc4add0fafb2aff16e",
        "merge": "e74c50970bbe1caa780cc85eb40f4b5c62f3b444",
        "required_state": "CLOSED_PASS",
        "projection_contract": "ACTIVATION_REGISTRY_PROJECT_CONTEXT_CANONICAL_GIT_PARITY_V0",
        "qualification_sha256": "f25d9305cbfe106b1b7295088140e9b6f4c2f8e041692ebea7e8f63630988304",
        "binding_mismatch_behavior": "BLOCK_AUTH",
    }
    assert hashlib.sha256(QUALIFICATION.read_bytes()).hexdigest() == AUTH["canonical_predecessor"]["qualification_sha256"]
    assert AUTH["pinned_dsh_identity"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
        "moving_tag_or_branch_allowed": False,
        "later_commit_allowed": False,
    }
    contract = AUTH["qualified_launch_contract"]
    assert contract["digest"] == "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
    assert contract["runtime_manifest_digest"] == "afcfa011de46bd9fccaa120b5612c24a5ace2b2c451591ddf8b67fb43a8ce321"
    assert contract["executable_identity_digest"] == "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
    assert contract["launch_policy_digest"] == "34d5ceabbd89eaa7520cb5d5b69fa938a4cf15132b5c37e98382c4f6aab53f28"


def test_exact_one_episode_finite_budgets_and_claim_at_most_once() -> None:
    episode = AUTH["episode_authority"]
    parent = AUTH["parent_authority"]
    child = AUTH["child_authority"]
    assert episode["episode_id"] == f"{EXECUTION_ID}#EPISODE_1"
    assert episode["episode_count"] == 1
    assert episode["live_episodes_max"] == 1
    assert episode["episode_consumed_initial"] is False
    assert episode["second_episode_allowed"] is False
    assert episode["whole_episode_retry_allowed"] is False
    assert parent["provider"] == "openai" and parent["model"] == "gpt-5-mini"
    assert parent["max_request_attempts"] == 8
    assert parent["max_tokens_per_request"] == 4096
    assert parent["max_total_spend_usd"] == 1.0
    assert parent["retry_policy"] == {"llm_retries": 0, "provider_retry": 0, "automatic_continuation": False}
    assert parent["attempt_9"] == "BLOCK_COST_BEFORE_PROVIDER_IO"
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["codex_calls_max"] == 2 and child["claude_calls_max"] == 2
    assert child["generic_child_tools"] == []
    assert child["alternate_delegation_routes"] == []
    assert child["background_delegation"] is False
    claim = AUTH["claim_contract"]
    assert claim["namespace"] == "refs/heads/qntylab-claims/"
    assert claim["remote_claim_ref"] == "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r1"
    assert claim["historical_claim_ref_rejected"] == "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0"
    assert claim["remote_claim_create_only_fail_if_exists"] is True
    assert claim["local_receipt_open_exclusive"] is True
    assert claim["claim_identity_binds_to"] == ["execution_project_id", "episode_id", "authorization_project_id"]
    assert claim["partial_claim_behavior"] == "BLOCK_NEVER_REPLAY"
    assert claim["crash_or_timeout_restores_authority"] is False
    assert claim["created_during_authorization_construction"] is False


def test_claude_policy_remains_hard_read_only() -> None:
    claude = AUTH["child_execution_policies"]["claude"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert claude["tools"] == ["Read", "Glob", "Grep"]
    assert claude["disallowed_tools"] == ["Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"]
    assert all(claude[key] is False for key in ("write_allowed", "edit_allowed", "bash_allowed", "agent_allowed", "task_allowed", "mcp_allowed", "delegation_allowed", "ask_user_question_allowed"))
    assert claude["permission_mode"] == "dontAsk"
    assert claude["setting_sources"] == []
    assert claude["strict_mcp_config"] is True
    assert claude["mcp_servers"] == {} and claude["agents"] == {}
    assert claude["plugins"] == [] and claude["persistence"] is False


def test_authorization_has_no_activation_or_live_side_effects() -> None:
    assert AUTH["activation_prerequisite"] == {
        "activation_exists_initial": False,
        "activation_creation_during_this_phase": False,
        "activation_project_id": EXECUTION_ID,
        "must_use_canonical_projection_contract": "ACTIVATION_REGISTRY_PROJECT_CONTEXT_CANONICAL_GIT_PARITY_V0",
        "must_be_present_on_canonical_master": True,
        "branch_local_activation_candidate_effective": False,
        "old_authorization_or_activation_satisfies": False,
    }
    assert AUTH["execution_authority_after_construction"] == {
        "available": False,
        "state": "AUTHORIZATION_ONLY_ACTIVATION_REQUIRED",
        "effective_execution_authority": False,
        "implementation_authorized": False,
        "implementation_completed": True,
        "activation_exists": False,
        "active_project_after_closure": "NONE",
        "future_execution_result_recorded": False,
        "stage_b_requires_separate_decision": True,
    }
    assert AUTH["construction_receipts"] == {
        "real_secret_read": False,
        "remote_claim_created": False,
        "local_claim_created": False,
        "episode_claimed": False,
        "episode_consumed": False,
        "dsh_invocations": 0,
        "public_model_requests": 0,
        "codex_real_child_turns": 0,
        "claude_real_child_turns": 0,
        "spend_usd": 0.0,
        "live_episodes": 0,
        "fixture_mutations": 0,
    }
    assert not list(ARTIFACT.glob("activation.json"))


def test_project_context_sees_no_active_execution_project() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    record = projects[AUTHORIZATION_ID]
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert record["state"] == "CLOSED_PASS"
    assert record["execution_project_id"] == EXECUTION_ID
    assert record["activation_exists"] is False
    assert record["effective_execution_authority"] is False
    assert record["implementation_authorized"] is False
    assert record["episode_consumed"] is False
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert [item for item in projects.values() if item["state"] == "ACTIVE"] == []


def test_historical_authority_cannot_substitute_for_fresh_lineage() -> None:
    rejected = AUTH["historical_authority_rejected"]
    assert rejected["authorization_project_id"] == OLD_AUTHORIZATION_ID
    assert rejected["activation_project_id"] == OLD_EXECUTION_ID
    assert rejected["substitution_allowed"] is False
    assert AUTH["historical_v1r3r2_authority_compatible"] is False
    assert AUTH["claim_contract"]["historical_claim_ref_rejected"] != AUTH["claim_contract"]["remote_claim_ref"]


def test_downstream_firewall_and_strict_no_live_boundary() -> None:
    boundary = AUTH["governance_boundary"]
    assert boundary["stage_b_authorized"] is False
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"
    assert boundary["promotion_authority"] == "NONE"
    assert boundary["authorization_phase_live_dsh_calls"] == 0
    assert boundary["authorization_phase_paid_model_calls"] == 0
    assert boundary["authorization_phase_codex_child_turns"] == 0
    assert boundary["authorization_phase_claude_child_turns"] == 0
    assert boundary["authorization_phase_spend_usd"] == 0.0
    assert AUTH["qnty_agent_eval"] == "NOT_APPLICABLE"
