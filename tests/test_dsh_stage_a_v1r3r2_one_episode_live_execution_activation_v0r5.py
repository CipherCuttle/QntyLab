from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r5/activation.json"
AUTHORIZATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r5/authorization.json"
SUCCESSOR_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/evidence/successor_contract.json"
)
MATERIALIZER_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/materializer/"
    "qntylab-materialize-stage-a-dsh-home.mjs"
)
LOCAL_STATE = Path(
    "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r5/episode-1"
)

MASTER = "415d15e807204cdaf83b14cb86d04b52cf11e61d"
CURRENT_CANONICAL_MASTER = "36e3085c18a747e3755097c97915f61f289d0835"
CANDIDATE = "96a66205f7737096eaa4aba3faff0d34ed8eb1ce"
AUTH_PREDECESSOR = "f2a3e7a9e39aac93c413d758a2f1f329cbe1fd79"
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R5"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R5"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CONTRACT_DIGEST = "50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de"
HISTORICAL_CONTRACT = "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r5"
AUTH_SHA256 = "ebc45ed593a3370a11906b760c9456a0f007a5824137077923bbc351d3ec1112"
AUTH_BLOB = "901ce6bfc06000534b91546c2c1fb60c001df880"
MATERIALIZER_SHA256 = "ce18ebb9bb65cc01a07509189437cd1041ad09afaaee5ba318a6e822d82a09be"
HOME_MANIFEST = "5356ba6df6e0f35a4cc90225e920e34ef25ce33e658f16f00ba5cb6b9eb704fb"
HOME_SCHEMA = "133d018700b0fc7a4de59d22bbcd1e87615d62b47582bc5a2a4e235d1fe1bcef"
RUNTIME_MANIFEST = "0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3"
EXECUTABLE = "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
LAUNCHER = "6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329"
POLICY = "7345ab145a0c98696ce8b9e6d815f4da98092f7be680467278464fb098a51589"
FIXTURE = "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_current_canonical_master_and_historical_candidate_binding_are_distinct() -> None:
    activation = _load(ACTIVATION_PATH)
    assert _git("rev-parse", "origin/master") == CURRENT_CANONICAL_MASTER
    assert activation["canonicalization"]["candidate_base_sha"] == MASTER
    assert activation["authorization_identity"]["candidate_commit"] == CANDIDATE
    assert _git("merge-base", "--is-ancestor", CANDIDATE, MASTER) == ""


def test_authorization_is_bound_to_exact_canonical_bytes_and_git_blob() -> None:
    activation = _load(ACTIVATION_PATH)
    path = str(AUTHORIZATION_PATH.relative_to(ROOT))
    canonical_bytes = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"origin/master:{path}"],
        check=True,
        capture_output=True,
    ).stdout
    assert activation["authorization_identity"]["canonical_content_sha256"] == AUTH_SHA256
    assert hashlib.sha256(canonical_bytes).hexdigest() == AUTH_SHA256
    assert activation["authorization_identity"]["git_blob_sha"] == AUTH_BLOB
    assert _git("rev-parse", f"origin/master:{path}") == AUTH_BLOB


def test_authorization_project_and_state_are_exact() -> None:
    activation = _load(ACTIVATION_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    assert activation["authorization_identity"]["project_id"] == AUTHORIZATION_ID
    assert activation["authorization_identity"]["canonical_merge"] == MASTER
    assert activation["authorization_identity"]["required_state"] == "CLOSED_PASS"
    assert authorization["project_id"] == AUTHORIZATION_ID
    assert authorization["phase_state"] == "CLOSED_PASS"


def test_activation_identity_is_candidate_only_until_exact_canonical_merge() -> None:
    activation = _load(ACTIVATION_PATH)
    canonicalization = activation["canonicalization"]
    assert activation["project_id"] == EXECUTION_ID
    assert activation["phase_state"] == "ACTIVE_CANDIDATE"
    assert activation["effective_execution_authority"] is False
    assert activation["effective_only_after_exact_canonical_merge"] is True
    assert activation["activation_consumes_live_episode"] is False
    assert activation["second_episode_authorized"] is False
    assert activation["whole_episode_retry_allowed"] is False
    assert activation["branch_local_candidate_does_not_self_authorize"] is True
    assert canonicalization["branch_local_candidate_does_not_self_authorize"] is True
    assert canonicalization["canonical_authorization_merge"] == MASTER
    assert canonicalization["future_canonical_activation_merge_commit_required"] is True


def test_authorization_predecessor_source_is_distinct_from_canonical_merge() -> None:
    activation = _load(ACTIVATION_PATH)
    assert activation["authorization_identity"]["authorization_predecessor_source"] == AUTH_PREDECESSOR
    assert activation["authorization_identity"]["canonical_merge"] == MASTER
    assert activation["canonicalization"]["authorization_predecessor_source"] == AUTH_PREDECESSOR


def test_successor_contract_is_exact_and_historical_a392_is_not_complete() -> None:
    activation = _load(ACTIVATION_PATH)
    qualified = activation["qualified_launch_contract"]
    successor = _load(SUCCESSOR_PATH)
    assert qualified["digest"] == CONTRACT_DIGEST
    assert qualified["digest"] == activation["runtime_identity"]["qualified_launch_contract_digest"]
    assert qualified["contract_artifact_sha256"] == "9bb1f217b9de60b92841ababf6075ccf46c1080f1416f5e5e29fd496a08b143e"
    assert qualified["contract_artifact_sha256"] == hashlib.sha256(SUCCESSOR_PATH.read_bytes()).hexdigest()
    assert successor.get("qualifiedContractDigest") != HISTORICAL_CONTRACT
    assert qualified["predecessor_contract_digest"] == HISTORICAL_CONTRACT
    assert qualified["predecessor_contract_role"] == "HISTORICAL_PREDECESSOR_ONLY"
    assert qualified["predecessor_contract_is_final_live_contract"] is False
    assert HISTORICAL_CONTRACT in qualified["superseded_digests_rejected"]


def test_production_materializer_identity_is_exact() -> None:
    activation = _load(ACTIVATION_PATH)
    materializer = activation["qualified_launch_contract"]["production_materializer"]
    assert materializer["digest"] == MATERIALIZER_SHA256
    assert materializer["only_production_dsh_home_authority"] is True
    assert materializer["requires_fresh_empty_destination"] is True
    assert materializer["caller_selected_persistent_dsh_home_allowed"] is False
    assert materializer["ambient_fallback_allowed"] is False
    assert hashlib.sha256(MATERIALIZER_PATH.read_bytes()).hexdigest() == MATERIALIZER_SHA256


def test_production_home_and_schema_are_exact() -> None:
    activation = _load(ACTIVATION_PATH)
    home = activation["qualified_launch_contract"]["production_dsh_home"]
    assert home["manifest_digest"] == HOME_MANIFEST
    assert home["manifest_schema_digest"] == HOME_SCHEMA
    assert home["whole_home_identity_required"] is True
    assert home["fresh_disposable_dsh_home_required"] is True
    assert home["caller_selected_persistent_dsh_home_forbidden"] is True
    assert home["ambient_fallback_forbidden"] is True


def test_runtime_executable_launcher_and_policy_identities_are_exact() -> None:
    activation = _load(ACTIVATION_PATH)
    runtime = activation["runtime_identity"]
    qualified = activation["qualified_launch_contract"]
    assert runtime["repository"] == "deepseek-ai/deepseek-harness"
    assert runtime["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert runtime["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert runtime["tag"] == "dsh-v0.1.0-rc.7"
    assert runtime["lockfile_digest"] == "f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea"
    assert runtime["runtime_manifest_digest"] == RUNTIME_MANIFEST
    assert runtime["executable_identity_digest"] == EXECUTABLE
    assert qualified["composite_launcher_digest"] == LAUNCHER
    assert qualified["launch_policy_digest"] == POLICY
    assert runtime["launch_policy_digest"] == POLICY


def test_parent_policy_is_frozen() -> None:
    parent = _load(ACTIVATION_PATH)["parent_policy"]
    assert parent == {
        "provider": "openai",
        "model": "gpt-5-mini",
        "route": "llm-pi-ai",
        "maximum_logical_requests": 8,
        "provider_internal_retries": 0,
        "automatic_continuation": False,
        "maximum_output_tokens": 4096,
        "hard_spend_cap_usd": "1.00",
        "attempt_9": "DENY_BEFORE_PROVIDER_WIRE_IO",
        "alternate_provider": "FORBIDDEN",
        "model_substitution": "FORBIDDEN",
    }


def test_child_order_and_limits_are_frozen() -> None:
    child = _load(ACTIVATION_PATH)["child_policy"]
    assert child["order"] == [
        "codex_initial",
        "claude_review",
        "codex_repair_if_critical_high",
        "claude_rereview_if_repaired",
    ]
    assert child["codex_maximum_turns"] == 2
    assert child["claude_maximum_turns"] == 2


def test_claude_is_hard_read_only() -> None:
    activation = _load(ACTIVATION_PATH)
    policy = activation["child_policy"]
    assert activation["claude_hard_read_only"] is True
    assert policy["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(policy["denied_tools"]) == {
        "Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"
    }
    assert policy["permission_mode"] == "dontAsk"
    assert policy["strict_mcp_config"] is True
    assert policy["mcp_servers"] == {}
    assert policy["agents"] == {}
    assert policy["plugins"] == []


def test_fixture_identity_is_exact_and_immutable() -> None:
    fixture = _load(ACTIVATION_PATH)["fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["fixture_digest"] == FIXTURE
    assert fixture["canonical_fixture_mutation_allowed"] is False
    assert fixture["mutable_paths"] == ["retry.py"]
    assert fixture["immutable_paths"] == ["TASK.md", "tests/test_retry.py"]


def test_v0r5_episode_and_claim_tuple_are_exact() -> None:
    activation = _load(ACTIVATION_PATH)
    episode = activation["episode_identity"]
    claim = activation["claim_contract"]
    assert episode == {
        "execution_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "episode_generation": "V0R5",
        "episode_count": 1,
        "episode_claimed": False,
        "episode_consumed": False,
        "claim_ref": CLAIM_REF,
    }
    assert claim["authorization_id"] == AUTHORIZATION_ID
    assert claim["activation_id"] == EXECUTION_ID
    assert claim["qualified_contract_digest"] == CONTRACT_DIGEST
    assert claim["remote_claim_ref"] == CLAIM_REF
    assert claim["state_dir"] == str(LOCAL_STATE)
    assert claim["remote_claim_exists"] is False
    assert claim["local_claim_exists"] is False


def test_v0r4_claim_namespace_cannot_substitute_v0r5() -> None:
    activation = _load(ACTIVATION_PATH)
    historical = activation["claim_contract"]["historical_claim_refs_rejected"]
    assert "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r4" in historical
    assert activation["claim_contract"]["remote_claim_ref"] != historical[-1]
    assert activation["project_id"] != "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4"


def test_remote_v0r5_claim_is_absent() -> None:
    assert _git("ls-remote", "origin", CLAIM_REF) == ""


def test_local_v0r5_claim_preserves_terminal_evidence() -> None:
    assert LOCAL_STATE.is_dir()
    assert (LOCAL_STATE / "claim-intent.json").is_file()
    assert (LOCAL_STATE / "claim.lock").is_file()
    assert not (LOCAL_STATE / "claim-receipt.json").exists()


def test_activation_does_not_consume_or_retry_the_episode() -> None:
    activation = _load(ACTIVATION_PATH)
    assert activation["activation_consumes_episode"] is False
    assert activation["episode_claimed"] is False
    assert activation["episode_consumed"] is False
    assert activation["active_execution_project"]["implementation_completed"] is False
    assert activation["active_execution_project"]["second_episode_authorized"] is False
    assert activation["active_execution_project"]["whole_episode_retry_allowed"] is False


def test_activation_secret_gate_is_after_non_secret_gates_without_secret_access() -> None:
    activation = _load(ACTIVATION_PATH)
    secret = activation["secret_binding_contract"]
    order = activation["canonical_gate_order"]
    assert secret["authorization_phase_secret_reads"] == 0
    assert secret["activation_phase_secret_reads"] == 0
    assert secret["real_secret_path_never_used_during_activation"] is True
    assert order.index("real secret read + environment injection") > order.index("all remaining non-secret gates")
    assert order.index("create-only claim") > order.index("real secret read + environment injection")


def test_activation_records_zero_provider_model_child_dsh_and_fixture_activity() -> None:
    activation = _load(ACTIVATION_PATH)
    receipt = activation["construction_receipts"]
    status = activation["execution_status"]
    assert receipt["claims_created"] == 0
    assert receipt["external_provider_requests"] == 0
    assert receipt["real_model_calls"] == 0
    assert receipt["real_codex_turns"] == 0
    assert receipt["real_claude_turns"] == 0
    assert receipt["live_dsh_calls"] == 0
    assert receipt["fixture_mutations"] == 0
    assert status["dsh_invocations"] == 0
    assert status["parent_requests"] == 0
    assert status["codex_real_child_turns"] == 0
    assert status["claude_real_child_turns"] == 0
    assert status["fixture_mutations"] == 0


def test_activation_records_zero_spend() -> None:
    activation = _load(ACTIVATION_PATH)
    assert activation["spend_usd"] == "0"
    assert activation["construction_receipts"]["spend_usd"] == "0"
    assert activation["execution_status"]["spend_usd"] == 0.0
    assert activation["parent_policy"]["hard_spend_cap_usd"] == "1.00"


def test_registry_preserves_closed_v0r5_and_current_authorization_candidate() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert projection["identity_by_project"][EXECUTION_ID]["effective"] is False
    project = projects[EXECUTION_ID]
    assert project["state"] == "CLOSED_BLOCKED"
    assert project["candidate_state"] == "CLOSED_BLOCKED"
    assert project["canonicalization_status"] == "CLOSED"
    assert project["implementation_authorized"] is False
    assert project["implementation_completed"] is True
    assert project["effective_execution_authority"] is False


def test_registry_preserves_one_episode_and_closed_downstream_authority() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    project = next(item for item in registry["project"] if item["project_id"] == EXECUTION_ID)
    assert project["authorized_live_episodes"] == 1
    assert project["second_episode_authorized"] is False
    assert project["whole_episode_retry_allowed"] is False
    assert project["episode_claimed"] is False
    assert project["episode_consumed"] is False
    assert project["stage_b_authorized"] is False
    assert project["qnty_runtime_authority"] == "NONE"
    assert project["trading_authority"] == "NONE"
    assert project["capital_authority"] == "NONE"


def test_future_action_time_merge_binding_and_closure_are_required() -> None:
    activation = _load(ACTIVATION_PATH)
    action_time = activation["canonicalization"]["canonical_action_time_source_identity"]
    assert action_time["required"] is True
    assert action_time["canonical_master"] == MASTER
    assert action_time["future_activation_merge_commit"] == "REQUIRED_AT_ACTION_TIME"
    assert activation["future_closure_required"] is True
    assert activation["execution_closure_pr_budget"] == 1
    assert activation["next_action"].startswith("MERGE_ACTIVATION_PR_AFTER_EXPLICIT_USER_AUTHORIZATION")


def test_action_gate_order_is_frozen() -> None:
    assert _load(ACTIVATION_PATH)["canonical_gate_order"] == [
        "canonical authorization identity",
        "canonical activation identity",
        "canonical action-time master/source identity",
        "successor contract 50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de",
        "materializer identity",
        "fresh destination policy",
        "production DSH_HOME materialization",
        "whole-home identity verification",
        "runtime manifest identity",
        "executable identity",
        "composite launcher/policy identity",
        "parent policy",
        "child policy",
        "workspace containment",
        "fixture identity",
        "claim absence",
        "all remaining non-secret gates",
        "real secret read + environment injection",
        "create-only claim",
        "actual DSH invocation",
        "bounded terminal recording",
    ]


def test_activation_firewall_denies_live_and_broader_authority() -> None:
    firewall = _load(ACTIVATION_PATH)["authority_firewall"]
    assert firewall["live_execution_authorized_this_phase"] is False
    assert firewall["activation_created_this_phase"] is True
    assert firewall["claim_authorized_this_phase"] is False
    assert firewall["real_provider_io_authorized_this_phase"] is False
    assert firewall["real_secret_read_authorized_this_phase"] is False
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
