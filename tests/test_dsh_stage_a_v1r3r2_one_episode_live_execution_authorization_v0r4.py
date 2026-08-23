from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ARTIFACT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r4"
AUTH_PATH = ARTIFACT / "authorization.json"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
COMPOSITE_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0"
CONTRACT_PATH = COMPOSITE_ROOT / "evidence/contract.json"
QUALIFICATION_PATH = COMPOSITE_ROOT / "evidence/qualification.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
V0R3_AUTH_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r3/authorization.json"
V0R3_ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r3/activation.json"
V0R3_CLOSURE_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_result_v0r3/execution_evidence.json"

AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R4"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r4"
A392 = "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
COMPOSITE_POLICY = "7345ab145a0c98696ce8b9e6d815f4da98092f7be680467278464fb098a51589"
COMPOSITE_LAUNCHER = "6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329"
HISTORICAL_DIGESTS = {
    "e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82",
    "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa",
    "c98c0a91d15c0875e3635e9791561af5bbb8588ff66d4144c822570b6227b666",
    "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1",
}


def test_only_a392_current_contract_is_acceptable_and_artifact_hashes_match() -> None:
    qualified = AUTH["qualified_launch_contract"]
    assert qualified["digest"] == A392 == CONTRACT["qualifiedContractDigest"]
    assert qualified["only_digest_authorized"] == A392
    assert qualified["launch_policy_digest"] == CONTRACT["digests"]["COMPOSITE_LAUNCH_POLICY_DIGEST"] == COMPOSITE_POLICY
    assert qualified["contract_artifact_sha256"] == hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert qualified["qualification_artifact_sha256"] == hashlib.sha256(QUALIFICATION_PATH.read_bytes()).hexdigest()
    assert set(qualified["superseded_digests_rejected"]) == HISTORICAL_DIGESTS
    assert A392 not in HISTORICAL_DIGESTS

    for stale in HISTORICAL_DIGESTS:
        candidate = deepcopy(AUTH)
        candidate["qualified_launch_contract"]["digest"] = stale
        assert candidate["qualified_launch_contract"]["digest"] != CONTRACT["qualifiedContractDigest"]


def test_composite_launcher_is_exact_and_substitute_launchers_fail_closed() -> None:
    qualified = AUTH["qualified_launch_contract"]
    runtime = AUTH["runtime_binding"]
    expected_path = (
        "experiments/research/qnty_agent_orchestration_control_contract_v0/"
        "dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/"
        "launcher/qntylab-launch-dsh.mjs"
    )
    assert qualified["composite_launcher_path"] == expected_path
    assert qualified["composite_launcher_digest"] == COMPOSITE_LAUNCHER
    assert runtime["composite_launcher_path"] == expected_path
    assert runtime["composite_launcher_digest"] == COMPOSITE_LAUNCHER
    assert AUTH["composite_launcher_binding"]["path"] == expected_path
    assert AUTH["composite_launcher_binding"]["digest"] == COMPOSITE_LAUNCHER
    assert AUTH["composite_launcher_binding"]["physical_launcher_alone_satisfies_v0r4"] is False
    assert AUTH["composite_launcher_binding"]["historical_stage_a_launcher_alone_satisfies_v0r4"] is False
    assert AUTH["composite_launcher_binding"]["wrapper_bypass_immediate_pre_spawn_revalidation"] is False
    assert Path(ROOT / expected_path).read_bytes()
    assert hashlib.sha256((ROOT / expected_path).read_bytes()).hexdigest() == COMPOSITE_LAUNCHER


def test_contract_component_identities_are_derived_from_canonical_contract() -> None:
    runtime = CONTRACT["components"]["runtimeIdentity"]
    physical = CONTRACT["components"]["compositeLaunchPolicy"]["physicalRuntimeBinding"]
    executable = CONTRACT["components"]["executableIdentity"]
    bound = AUTH["runtime_binding"]
    assert bound["source_identity"]["commit"] == runtime["sourceIdentity"]["commit"]
    assert bound["source_identity"]["tree"] == runtime["sourceIdentity"]["tree"]
    assert bound["source_identity"]["tag"] == runtime["sourceIdentity"]["tag"]
    assert bound["runtime_manifest_digest"] == CONTRACT["digests"]["RUNTIME_MANIFEST_DIGEST"]
    assert bound["executable_identity_digest"] == CONTRACT["digests"]["EXECUTABLE_IDENTITY_DIGEST"]
    assert bound["lockfile_digest"] == runtime["lockfileDigest"]
    assert bound["built_cli_digest"] == runtime["builtCliDigest"]
    assert bound["physical_launcher_digest"] == physical["physicalLauncher"]["digest"]
    assert executable["nodeExecutableDigest"]
    assert executable["pythonExecutableDigest"]
    assert executable["codexExecutableDigest"]
    assert executable["claudeExecutableDigest"]


def test_v0r3_is_closed_blocked_and_never_substituted() -> None:
    predecessor = AUTH["predecessor_closure"]
    v0r3 = json.loads(V0R3_AUTH_PATH.read_text(encoding="utf-8"))
    activation = json.loads(V0R3_ACTIVATION_PATH.read_text(encoding="utf-8"))
    closure = json.loads(V0R3_CLOSURE_PATH.read_text(encoding="utf-8"))
    assert predecessor["project_id"] == "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
    assert predecessor["state"] == "CLOSED_BLOCKED"
    assert predecessor["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert predecessor["episode_claimed"] is False
    assert predecessor["episode_consumed"] is False
    assert predecessor["rerun_authorized"] is False
    assert v0r3["project_id"] != AUTHORIZATION_ID
    assert activation["project_id"] != EXECUTION_ID
    assert activation["episode_identity"]["episode_id"] != EPISODE_ID
    assert activation["claim_contract"]["remote_claim_ref"] != CLAIM_REF
    assert closure["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert closure["closure"]["project_state_after"] == "CLOSED_BLOCKED"
    assert closure["closure"]["active_project_after_closure"] == "NONE"


def test_fresh_authorization_episode_and_claim_tuple_are_exactly_one_and_collision_free() -> None:
    fresh = AUTH["fresh_identity"]
    episode = AUTH["episode_authority"]
    claim = AUTH["claim_contract"]
    assert AUTH["project_id"] == AUTHORIZATION_ID
    assert fresh["future_activation_project_id"] == EXECUTION_ID
    assert fresh["episode_id"] == EPISODE_ID
    assert fresh["claim_remote_ref"] == CLAIM_REF
    assert fresh["collision_free_successor"] is True
    assert fresh["v0r3_reused"] is False
    assert episode["live_episodes_max"] == episode["episode_count"] == 1
    assert episode["second_episode_allowed"] is False
    assert episode["whole_episode_retry_allowed"] is False
    assert episode["activation_consumes_episode"] is False
    assert episode["authorization_construction_consumes_episode"] is False
    assert claim["future_execution_tuple"] == {
        "authorization_project_id": AUTHORIZATION_ID,
        "activation_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "qualified_contract_digest": A392,
        "canonical_master": "add590cac0afebd9666a3453b38ae19866b9dea5",
    }
    assert claim["remote_claim_exists_at_construction"] is False
    assert claim["local_claim_exists_at_construction"] is False
    assert not Path(fresh["claim_local_path"]).exists()


def test_fresh_activation_artifact_was_not_present_in_canonical_history() -> None:
    activation_relative = (
        "experiments/research/qnty_agent_orchestration_control_contract_v0/"
        "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r4/activation.json"
    )
    result = subprocess.run(
        ["git", "log", "origin/master", "--oneline", "--", activation_relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""


def test_parent_policy_is_the_canonical_ceiling() -> None:
    expected = CONTRACT["components"]["compositeLaunchPolicy"]["parentPolicy"]
    parent = AUTH["parent_authority"]
    assert parent["provider"] == expected["provider"] == "openai"
    assert parent["model"] == expected["model"] == "gpt-5-mini"
    assert parent["route"] == expected["route"] == "llm-pi-ai"
    assert parent["max_request_attempts"] == expected["maximumLogicalRequests"] == 8
    assert parent["provider_internal_retries"] == expected["providerInternalRetries"] == 0
    assert parent["automatic_continuation"] is expected["automaticContinuation"] is False
    assert parent["max_output_tokens_per_request"] == expected["maximumOutputTokens"] == 4096
    assert AUTH["spend_authority"]["cap_usd"] == expected["authorizedSpendCapUsd"] == "1.00"
    assert AUTH["spend_authority"]["price_schedule_id"] == expected["priceScheduleId"]
    assert parent["alternate_provider_allowed"] is False
    assert parent["model_substitution_allowed"] is False


def test_child_controller_and_claude_policy_are_hard_frozen() -> None:
    expected = CONTRACT["components"]["compositeLaunchPolicy"]
    child = AUTH["child_authority"]
    assert child["model_facing_tools"] == expected["childPolicy"]["modelFacingTools"]
    assert child["codex_calls_max"] == expected["childPolicy"]["codexMaximum"] == 2
    assert child["claude_calls_max"] == expected["childPolicy"]["claudeMaximum"] == 2
    assert child["background_delegation"] is False
    assert child["generic_child_tools"] == []
    assert child["alternate_delegation_routes"] == []
    assert child["state_machine"][0].startswith("INITIAL -> Codex".replace("Codex", "INITIAL_CODEX"))
    claude = AUTH["child_execution_policies"]["claude"]
    canonical_claude = expected["claudePolicy"]
    assert claude["allowed_tools"] == canonical_claude["allowedTools"] == ["Read", "Glob", "Grep"]
    assert claude["disallowed_tools"] == canonical_claude["disallowedTools"]
    assert claude["permission_mode"] == canonical_claude["permissionMode"] == "dontAsk"
    assert claude["setting_sources"] == canonical_claude["settingSources"] == []
    assert claude["strict_mcp_config"] is canonical_claude["strictMcpConfig"] is True
    assert claude["mcp_servers"] == canonical_claude["mcpServers"] == {}
    assert claude["agents"] == canonical_claude["agents"] == {}
    assert claude["plugins"] == canonical_claude["plugins"] == []
    assert claude["persistence"] is canonical_claude["persistence"] is False
    for denied in ("write_allowed", "edit_allowed", "bash_allowed", "agent_allowed", "task_allowed", "mcp_allowed", "delegation_allowed"):
        assert claude[denied] is False


def test_secret_claim_and_action_time_gate_order_are_fail_closed() -> None:
    secret = AUTH["secret_binding_contract"]
    assert secret["source_path"] == "~/.secrets/openai_api_key_stage_a"
    assert secret["auth_env"] == "OPENAI_API_KEY"
    assert secret["authorization_phase_secret_reads"] == 0
    assert secret["content_embedded"] is False
    assert secret["hashed"] is False
    assert secret["logged"] is False
    assert secret["serialized"] is False
    assert secret["persisted"] is False
    assert AUTH["claim_contract"]["created_during_authorization_construction"] is False
    order = AUTH["action_time_gate_order"]
    assert order.index("canonical activation") > order.index("canonical authorization")
    assert order.index("verify secret file availability/readability/nonempty") > order.index("remaining non-secret gates and authority firewall")
    assert order.index("read secret into memory only and bind OPENAI_API_KEY through explicit extraEnv") > order.index("verify secret file availability/readability/nonempty")
    assert order.index("create fresh durable at-most-once claim") > order.index("read secret into memory only and bind OPENAI_API_KEY through explicit extraEnv")
    assert order.index("complete claim before provider I/O") > order.index("create fresh durable at-most-once claim")
    assert order.index("allow DSH/provider I/O only after successful claim") > order.index("complete claim before provider I/O")


def test_timeout_replay_firewall_and_authorization_effect_are_closed() -> None:
    timeout = AUTH["timeout_policy"]
    assert timeout["live_episode_timeout_seconds"] == 1800
    assert timeout["timeout_allows_rerun"] is False
    assert timeout["terminal_failure_allows_rerun"] is False
    assert timeout["claim_crossed_timeout_or_crash_behavior"] == "BLOCK_NEVER_REPLAY"
    assert timeout["new_authority_required_after_closure"] is True
    firewall = AUTH["authority_firewall"]
    assert firewall["authorization_effective"] is False
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
    assert firewall["broader_production_authority"] == "NONE"
    effect = AUTH["execution_authority_after_construction"]
    assert effect["effective_execution_authority"] is False
    assert effect["active_project"] == "NONE"
    assert effect["activation_exists"] is False
    assert effect["episode_claimed"] is False
    assert effect["episode_consumed"] is False
    assert AUTH["activation_prerequisite"]["activation_creation_during_this_phase"] is False


def test_authorization_construction_has_zero_external_activity() -> None:
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


def test_project_context_remains_inactive_and_v0r3_registry_row_is_immutable() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    authorization = projects[AUTHORIZATION_ID]
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["implementation_authorized"] is False
    assert authorization["implementation_completed"] is True
    assert authorization["active_project_after_closure"] == "NONE"
    v0r3 = projects["DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"]
    assert v0r3["state"] == "CLOSED_BLOCKED"
    assert v0r3["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert v0r3["episode_claimed"] is False
    assert v0r3["episode_consumed"] is False
    assert v0r3["timeout_allows_rerun"] is False


def test_next_action_and_review_policy_stop_at_authorization() -> None:
    assert AUTH["terminal_verdict"] == "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_AUTHORIZATION_V0R4_READY"
    assert "SEPARATE V0R4 ACTIVATION" in AUTH["next_action"]
    assert "Do not activate, execute, read the secret, create a claim" in AUTH["next_action"]
    review = AUTH["review_policy"]
    assert review["exactly_one_independent_hostile_review_required"] is True
    assert review["hostile_review_completed"] is True
    assert review["hostile_review_count"] == 1
    assert review["critical_findings"] == 0
    assert review["high_findings"] == 0
    assert review["targeted_rereview_used"] is False
