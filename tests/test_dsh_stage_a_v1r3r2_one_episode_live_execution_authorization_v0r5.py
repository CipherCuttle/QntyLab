from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ARTIFACT_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r5"
AUTH_PATH = ARTIFACT_ROOT / "authorization.json"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
SUCCESSOR_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0"
SUCCESSOR_PATH = SUCCESSOR_ROOT / "evidence/successor_contract.json"
SUCCESSOR = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
V0R4_AUTH_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r4/authorization.json"
V0R4 = json.loads(V0R4_AUTH_PATH.read_text(encoding="utf-8"))

AUTH_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R5"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R5"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CANONICAL_MASTER = "f2a3e7a9e39aac93c413d758a2f1f329cbe1fd79"
SUCCESSOR_DIGEST = "50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de"
A392 = "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
CLAIM_REPAIR_AUTHORIZATION_PROJECT_ID = "DSH_STAGE_A_CLAIM_ACQUISITION_TRANSPORT_AND_OBSERVABILITY_REPAIR_AUTHORIZATION_V0"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _blob_exists(commit: str, path: str) -> bool:
    return _git("cat-file", "-e", f"{commit}:{path}").returncode == 0


def test_canonical_predecessor_merge_and_successor_contract_are_exact() -> None:
    parents = _git("rev-list", "--parents", "-n", "1", CANONICAL_MASTER).stdout.split()
    assert parents == [
        CANONICAL_MASTER,
        "838b6e03608e4c2bc686a4f571dfbb340a333ddb",
        "a2b384f3d774767808413df3f68418828346fd99",
    ]
    binding = AUTH["successor_contract_binding"]
    assert binding["qualified_launch_contract_digest"] == SUCCESSOR_DIGEST
    assert binding["predecessor_contract_digest"] == A392
    assert binding["artifact_sha256"] == hashlib.sha256(SUCCESSOR_PATH.read_bytes()).hexdigest()
    assert SUCCESSOR["NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST"] == SUCCESSOR_DIGEST
    assert SUCCESSOR["contract"]["projectId"] == "DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_REQUALIFICATION_V0"
    assert SUCCESSOR["contract"]["LIVE_AUTHORITY"] is False
    assert SUCCESSOR["contract"]["separateV0R5AuthorizationRequired"] is True
    assert SUCCESSOR["contract"]["v0r5Created"] is False


def test_materializer_home_manifest_and_runtime_identities_are_recomputed() -> None:
    binding = AUTH["successor_contract_binding"]
    materializer = ROOT / binding["production_dsh_home_materializer"]["path"]
    assert hashlib.sha256(materializer.read_bytes()).hexdigest() == binding["production_dsh_home_materializer"]["digest"]
    assert binding["production_dsh_home_materializer"]["digest"] == SUCCESSOR["NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST"]
    assert binding["dsh_home_manifest"]["schema_digest"] == SUCCESSOR["NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST"]
    assert binding["dsh_home_manifest"]["production_home_digest"] == SUCCESSOR["contract"]["productionDshHomeIdentity"]["homeManifestDigest"]
    assert binding["runtime_identity"]["runtime_manifest_digest"] == SUCCESSOR["contract"]["runtimeManifestDigest"]
    assert binding["runtime_identity"]["executable_identity_digest"] == SUCCESSOR["contract"]["executableIdentityDigest"]
    assert binding["composite_launcher"]["digest"] == SUCCESSOR["contract"]["compositeLauncher"]["digest"]
    assert binding["composite_launch_policy_digest"] == SUCCESSOR["contract"]["compositeLaunchPolicyDigest"]
    assert binding["production_dsh_home_materializer"]["only_production_dsh_home_authority"] is True
    assert binding["production_dsh_home_materializer"]["caller_selected_persistent_dsh_home_allowed"] is False


def test_a392_is_historical_only_and_v0r4_is_closed_immutable_and_not_reusable() -> None:
    assert A392 in AUTH["historical_authority_rejected"]["qualified_contract_digests"]
    assert AUTH["successor_contract_binding"]["qualified_launch_contract_digest"] != A392
    assert AUTH["v0r4_closure"] == {
        "project_id": "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4",
        "state": "CLOSED_BLOCKED",
        "terminal_outcome": "BLOCK_RUNTIME_IDENTITY",
        "episode_claimed": False,
        "episode_consumed": False,
        "rerun_authorized": False,
        "reopen_allowed": False,
        "claim_tuple_reusable": False,
        "historical_evidence_immutable": True,
    }
    assert V0R4["project_id"] != AUTH_ID
    assert V0R4["fresh_identity"]["claim_remote_ref"] != AUTH["fresh_identity"]["claim_remote_ref"]
    assert V0R4["qualified_launch_contract"]["digest"] == A392


def test_fresh_v0r5_identity_claim_absence_and_single_episode_policy_are_exact() -> None:
    fresh = AUTH["fresh_identity"]
    claim = AUTH["claim_contract"]
    assert AUTH["project_id"] == AUTH_ID
    assert fresh["future_activation_project_id"] == EXECUTION_ID
    assert fresh["episode_id"] == EPISODE_ID
    assert fresh["claim_remote_ref"].endswith("-v0r5")
    assert fresh["claim_remote_ref"] != V0R4["fresh_identity"]["claim_remote_ref"]
    assert fresh["collision_free_successor"] is True
    assert fresh["v0r4_reused"] is False
    assert AUTH["episode_authority"]["episode_count"] == 1
    assert AUTH["episode_authority"]["second_episode_allowed"] is False
    assert AUTH["episode_authority"]["whole_episode_retry_allowed"] is False
    assert claim["future_execution_tuple"] == {
        "authorization_project_id": AUTH_ID,
        "activation_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "qualified_contract_digest": SUCCESSOR_DIGEST,
        "canonical_master": CANONICAL_MASTER,
    }
    assert claim["created_during_authorization_construction"] is False
    assert claim["remote_claim_exists_at_construction"] is False
    assert claim["local_claim_exists_at_construction"] is False
    local_state = Path(fresh["claim_local_path"])
    assert local_state.is_dir()
    assert (local_state / "claim-intent.json").is_file()
    assert (local_state / "claim.lock").is_file()
    assert not (local_state / "claim-receipt.json").exists()
    assert V0R4["fresh_identity"]["claim_remote_ref"] in claim["historical_claim_refs_rejected"]


def test_parent_child_secret_and_fail_closed_order_are_frozen() -> None:
    parent = AUTH["parent_policy"]
    assert (parent["provider"], parent["model"]) == ("openai", "gpt-5-mini")
    assert parent["maximum_logical_requests"] == 8
    assert parent["provider_internal_retries"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["maximum_output_tokens"] == 4096
    assert parent["hard_spend_cap_usd"] == "1.00"
    child = AUTH["child_policy"]
    assert child["codex_maximum_turns"] == 2
    assert child["claude_maximum_turns"] == 2
    claude = child["claude"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(claude["disallowed_tools"]) >= {"Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"}
    assert all(claude[key] is False for key in ("write_allowed", "edit_allowed", "bash_allowed", "agent_allowed", "task_allowed", "mcp_allowed", "ask_user_question_allowed", "delegation_allowed"))
    assert AUTH["secret_policy"]["authorization_phase_secret_reads"] == 0
    assert AUTH["secret_policy"]["real_secret_path_never_used_during_authorization"] is True
    order = AUTH["action_time_gate_order"]
    assert order.index("secret read / environment injection") > order.index("all other non-secret live gates")
    assert order.index("create-only claim") > order.index("secret read / environment injection")
    assert order.index("actual DSH invocation") > order.index("create-only claim")


def test_authorization_has_zero_external_activity_and_cannot_self_activate() -> None:
    assert AUTH["construction_receipts"] == {
        "secret_reads": 0,
        "claims_created": 0,
        "dsh_calls": 0,
        "public_provider_requests": 0,
        "real_model_calls": 0,
        "real_codex_turns": 0,
        "real_claude_turns": 0,
        "fixture_mutations": 0,
        "activation_artifacts_created": 0,
        "spend_usd": "0",
    }
    firewall = AUTH["authority_firewall"]
    assert firewall["v0r5_created"] is False
    assert firewall["v0r5_activated"] is False
    assert firewall["live_execution_performed"] is False
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["active_project_after_closure"] == "NONE"
    assert AUTH["canonicalization"]["branch_local_artifact_does_not_self_authorize"] is True
    assert AUTH["canonicalization"]["canonical_presence_required_before_activation"] is True
    auth_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r5/authorization.json"
    activation_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_v0r5/activation.json"
    assert not _blob_exists(CANONICAL_MASTER, auth_rel)
    activation = json.loads((ROOT / activation_rel).read_text(encoding="utf-8"))
    assert activation["phase_state"] == "ACTIVE_CANDIDATE"
    assert activation["effective_execution_authority"] is False
    assert activation["branch_local_candidate_does_not_self_authorize"] is True


def test_project_context_registry_projection_is_inactive_and_consistent() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    row = projects[AUTH_ID]
    assert row["state"] == "CLOSED_PASS"
    assert row["implementation_authorized"] is False
    assert row["implementation_completed"] is True
    assert row["activation_exists"] is False
    assert row["effective_execution_authority"] is False
    assert row["qualified_launch_contract_digest"] == SUCCESSOR_DIGEST
    assert row["production_materializer_digest"] == AUTH["successor_contract_binding"]["production_dsh_home_materializer"]["digest"]
    assert row["dsh_home_manifest_schema_digest"] == AUTH["successor_contract_binding"]["dsh_home_manifest"]["schema_digest"]
    assert row["dsh_home_manifest_digest"] == AUTH["successor_contract_binding"]["dsh_home_manifest"]["production_home_digest"]
    assert row["claim_created"] is False
    assert row["authorization_phase_secret_reads"] == 0
    assert row["active_project_after_closure"] == "NONE"


def test_terminal_semantics_cover_required_fail_closed_classes() -> None:
    required = {
        "SUCCESS", "BLOCK_AUTH", "BLOCK_RUNTIME_IDENTITY", "BLOCK_CONTRACT_IDENTITY",
        "BLOCK_DSH_HOME_MATERIALIZATION", "BLOCK_WORKSPACE", "BLOCK_FIXTURE_IDENTITY",
        "BLOCK_SECRET", "BLOCK_CLAIM", "BLOCK_NEVER_REPLAY", "BLOCK_PARENT_POLICY",
        "BLOCK_CHILD_POLICY", "BLOCK_PROVIDER", "BLOCK_DSH", "BLOCK_OUTPUT_VALIDATION",
    }
    assert required == set(AUTH["terminal_semantics"]["classes"])
    assert AUTH["terminal_semantics"]["no_success_after_partial_execution"] is True
    assert AUTH["terminal_semantics"]["ambiguous_claim_result"] == "BLOCK_NEVER_REPLAY"
