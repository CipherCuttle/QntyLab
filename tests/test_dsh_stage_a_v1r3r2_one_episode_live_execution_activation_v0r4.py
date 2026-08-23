from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r4/activation.json"
AUTHORIZATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r4/authorization.json"
CONTRACT_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/contract.json"
)
QUALIFICATION_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/qualification.json"
)
COMPOSITE_LAUNCHER_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/launcher/qntylab-launch-dsh.mjs"
)
V0R3_AUTHORIZATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r3/authorization.json"
V0R3_ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r3/activation.json"
V0R3_CLOSURE_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_result_v0r3/execution_evidence.json"

AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R4"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r4"
LOCAL_STATE = Path("/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r4/episode-1")
A392 = "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
POLICY = "7345ab145a0c98696ce8b9e6d815f4da98092f7be680467278464fb098a51589"
LAUNCHER = "6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329"
AUTHORIZATION_SHA = "8ae1ba578f7db2a59a5edda22e8ece50237f1d7315eb8dcbfd9333b251134084"
CANONICAL_MASTER = "b5defe87e0f5b01450899c74d881149863a4d7c2"
HISTORICAL_DIGESTS = {
    "e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82",
    "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa",
    "c98c0a91d15c0875e3635e9791561af5bbb8588ff66d4144c822570b6227b666",
    "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(root),
            "-c", "user.name=activation-test",
            "-c", "user.email=activation-test@example.invalid",
            "commit", "-qm", message,
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _source_record() -> dict:
    _, _, registry = project_context.load_context_sources(ROOT)
    return copy.deepcopy(next(item for item in registry["project"] if item["project_id"] == EXECUTION_ID))


def _synthetic_repo(tmp_path: Path, *, canonical: bool) -> tuple[Path, dict]:
    root = tmp_path / ("canonical" if canonical else "candidate")
    sources = (ACTIVATION_PATH, AUTHORIZATION_PATH, CONTRACT_PATH, QUALIFICATION_PATH)
    for source in sources:
        destination = root / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    base_sha = _commit(root, "base")

    activation_path = root / ACTIVATION_PATH.relative_to(ROOT)
    activation = _load(activation_path)
    activation["canonicalization"]["candidate_base_sha"] = base_sha
    activation["canonicalization"]["canonical_predecessor_merge"] = base_sha
    activation["canonicalization"]["canonical_authorization_merge"] = base_sha
    activation["authorization_identity"]["candidate_commit"] = base_sha
    activation["authorization_identity"]["canonical_merge"] = base_sha
    authorization_path = root / AUTHORIZATION_PATH.relative_to(ROOT)
    activation["authorization_identity"]["canonical_content_sha256"] = hashlib.sha256(
        authorization_path.read_bytes()
    ).hexdigest()
    activation["authorization_identity"]["git_blob_sha"] = subprocess.run(
        ["git", "-C", str(root), "hash-object", str(authorization_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    activation_path.write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")

    record = _source_record()
    record["canonical_predecessor_merge"] = base_sha
    record["authorization_candidate_commit"] = base_sha
    record["authorization_canonical_merge"] = base_sha
    candidate_sha = _commit(root, "V0R4 activation candidate")
    canonical_sha = candidate_sha if canonical else base_sha
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/master", canonical_sha], check=True
    )
    return root, record


def test_v0r4_activation_binds_canonical_authorization_bytes_and_merge() -> None:
    activation = _load(ACTIVATION_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    canonical_bytes = subprocess.run(
        ["git", "show", f"origin/master:{AUTHORIZATION_PATH.relative_to(ROOT)}"],
        check=True,
        capture_output=True,
    ).stdout
    assert activation["authorization_identity"]["project_id"] == AUTHORIZATION_ID
    assert activation["authorization_identity"]["artifact"] == str(AUTHORIZATION_PATH.relative_to(ROOT))
    assert activation["authorization_identity"]["canonical_merge"] == CANONICAL_MASTER
    assert activation["canonicalization"]["candidate_base_sha"] == CANONICAL_MASTER
    assert activation["authorization_identity"]["canonical_content_sha256"] == AUTHORIZATION_SHA
    assert hashlib.sha256(canonical_bytes).hexdigest() == AUTHORIZATION_SHA
    assert activation["authorization_identity"]["git_blob_sha"] == subprocess.run(
        ["git", "rev-parse", f"origin/master:{AUTHORIZATION_PATH.relative_to(ROOT)}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert authorization["project_id"] == AUTHORIZATION_ID
    assert authorization["phase_state"] == "CLOSED_PASS"


def test_v0r4_contract_and_composite_launcher_are_exact() -> None:
    activation = _load(ACTIVATION_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    contract = _load(CONTRACT_PATH)
    qualified = activation["qualified_launch_contract"]
    assert qualified["digest"] == A392 == authorization["qualified_launch_contract"]["digest"]
    assert qualified["digest"] == contract["qualifiedContractDigest"]
    assert qualified["launch_policy_digest"] == POLICY
    assert qualified["contract_artifact_sha256"] == hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert qualified["qualification_artifact_sha256"] == hashlib.sha256(QUALIFICATION_PATH.read_bytes()).hexdigest()
    assert qualified["composite_launcher_digest"] == LAUNCHER
    assert hashlib.sha256(COMPOSITE_LAUNCHER_PATH.read_bytes()).hexdigest() == LAUNCHER
    assert qualified["composite_launcher_path"] != (
        "experiments/research/qnty_agent_orchestration_control_contract_v0/"
        "dsh_runtime_materialization_and_launch_v0/launcher/qntylab-launch-dsh.mjs"
    )
    assert qualified["composite_launcher_path"] != (
        "experiments/research/qnty_agent_orchestration_control_contract_v0/"
        "dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/launcher/qntylab-launch-dsh.mjs"
    )
    assert set(qualified["superseded_digests_rejected"]) == HISTORICAL_DIGESTS
    assert qualified["digest"] not in HISTORICAL_DIGESTS


def test_v0r4_rejects_v0r3_identity_and_preserves_closure() -> None:
    activation = _load(ACTIVATION_PATH)
    auth = _load(AUTHORIZATION_PATH)
    v0r3_auth = _load(V0R3_AUTHORIZATION_PATH)
    v0r3_activation = _load(V0R3_ACTIVATION_PATH)
    v0r3_closure = _load(V0R3_CLOSURE_PATH)
    assert activation["project_id"] == EXECUTION_ID
    assert activation["episode_identity"]["episode_id"] == EPISODE_ID
    assert activation["claim_contract"]["remote_claim_ref"] == CLAIM_REF
    assert activation["project_id"] != v0r3_activation["project_id"]
    assert auth["predecessor_closure"]["project_id"] == v0r3_auth["fresh_identity"]["future_activation_project_id"]
    assert auth["predecessor_closure"]["state"] == "CLOSED_BLOCKED"
    assert auth["predecessor_closure"]["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert v0r3_closure["project_id"] == "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
    assert v0r3_closure["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"


def test_v0r4_exact_episode_claim_and_timeout_firewalls() -> None:
    activation = _load(ACTIVATION_PATH)
    episode = activation["episode_authority"]
    claim = activation["claim_contract"]
    timeout = activation["timeout_policy"]
    assert activation["episode_identity"] == {
        "execution_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "episode_generation": "V0R4",
        "episode_count": 1,
        "episode_claimed": False,
        "episode_consumed": False,
        "claim_ref": CLAIM_REF,
    }
    assert episode["live_episodes_max"] == episode["episode_count"] == 1
    assert episode["second_episode_allowed"] is False
    assert episode["whole_episode_retry_allowed"] is False
    assert claim["state_dir"] == str(LOCAL_STATE)
    assert claim["remote_claim_exists"] is False
    assert claim["local_claim_exists"] is False
    assert claim["created_during_activation_construction"] is False
    assert not LOCAL_STATE.exists()
    assert timeout["live_episode_timeout_seconds"] == 1800
    assert timeout["timeout_allows_rerun"] is False
    assert timeout["claim_crossed_timeout_or_crash_behavior"] == "BLOCK_NEVER_REPLAY"


def test_v0r4_parent_child_secret_and_authority_policy_are_frozen() -> None:
    activation = _load(ACTIVATION_PATH)
    parent = activation["parent_authority"]
    child = activation["child_authority"]
    claude = activation["claude_policy"]
    secret = activation["secret_binding_contract"]
    firewall = activation["authority_firewall"]
    assert parent["provider"] == "openai"
    assert parent["model"] == "gpt-5-mini"
    assert parent["route"] == "llm-pi-ai"
    assert parent["max_request_attempts"] == 8
    assert parent["attempt_9"] == "DENY_BEFORE_PROVIDER_WIRE_IO"
    assert parent["provider_internal_retries"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["max_output_tokens_per_request"] == 4096
    assert parent["max_input_tokens_upper_bound"] == 123904
    assert parent["max_total_spend_usd"] == 1.0
    assert parent["alternate_provider_allowed"] is False
    assert parent["model_substitution_allowed"] is False
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["codex_calls_max"] == child["claude_calls_max"] == 2
    assert child["background_delegation"] is False
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(claude["denied_tools"]) == {"Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"}
    assert all(claude[key] is False for key in ("write_allowed", "edit_allowed", "bash_allowed", "agent_allowed", "task_allowed", "mcp_allowed", "ask_user_question_allowed", "delegation_allowed", "mcp_allowed"))
    assert claude["permission_mode"] == "dontAsk"
    assert claude["setting_sources"] == []
    assert claude["strict_mcp_config"] is True
    assert claude["mcp_servers"] == {} and claude["agents"] == {} and claude["plugins"] == []
    assert claude["persistence"] is False
    assert secret["source_path"] == "~/.secrets/openai_api_key_stage_a"
    assert secret["auth_env"] == "OPENAI_API_KEY"
    assert secret["authorization_phase_secret_reads"] == 0
    assert secret["content_embedded"] is False
    assert secret["explicit_extra_env_required"] is True
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["trading_authority"] == firewall["capital_authority"] == firewall["promotion_authority"] == "NONE"


def test_v0r4_action_gate_order_and_construction_counters_are_closed() -> None:
    activation = _load(ACTIVATION_PATH)
    order = activation["canonical_gate_order"]
    counters = activation["construction_receipts"]
    assert order.index("real secret read") > order.index("ALL OTHER NON-SECRET GATES")
    assert order.index("durable local claim intent") > order.index("explicit extraEnv binding validation")
    assert order.index("first potentially paid parent dispatch") > order.index("prove complete claim")
    assert counters == {
        "activation_artifacts_created": 1,
        "claims_created": 0,
        "claim_creations": 0,
        "external_provider_requests": 0,
        "fixture_mutations": 0,
        "live_dsh_calls": 0,
        "real_claude_child_turns": 0,
        "real_codex_child_turns": 0,
        "real_secret_reads": 0,
        "spend_usd": "0",
    }
    assert activation["execution_status"]["dsh_invocations"] == 0
    assert activation["execution_status"]["parent_requests"] == 0
    assert activation["execution_status"]["codex_real_child_turns"] == 0
    assert activation["execution_status"]["claude_real_child_turns"] == 0
    assert activation["execution_status"]["fixture_mutations"] == 0
    assert activation["effective_execution_authority"] is False


def test_branch_local_activation_is_not_effective_and_registry_candidate_is_exact() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    identity = projection["identity_by_project"][EXECUTION_ID]
    assert identity["effective"] is False
    assert projects[EXECUTION_ID]["state"] == "ACTIVE"
    assert projects[EXECUTION_ID]["episode_id"] == EPISODE_ID
    assert projects[EXECUTION_ID]["episode_claimed"] is False
    assert projects[EXECUTION_ID]["episode_consumed"] is False
    assert projects["DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"]["state"] == "CLOSED_BLOCKED"


def test_synthetic_canonical_merge_projects_exactly_one_v0r4_episode(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, canonical=True)
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == EXECUTION_ID
    assert projection["active_project"]["state"] == "ACTIVE"
    assert projection["active_project"]["implementation_authorized"] is True
    assert projection["active_project"]["episode_id"] == EPISODE_ID
    assert projection["active_project"]["episode_claimed"] is False
    assert projection["active_project"]["episode_consumed"] is False
    assert projection["active_project"]["authorized_live_episodes"] == 1
    assert projection["active_project"]["second_episode_authorized"] is False
    assert projection["active_project"]["whole_episode_retry_allowed"] is False


def test_synthetic_candidate_merge_cannot_self_authorize(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, canonical=False)
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert projection["identity_by_project"][EXECUTION_ID]["effective"] is False


def test_canonical_authorization_bytes_cannot_be_substituted_locally(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, canonical=True)
    authorization_path = root / AUTHORIZATION_PATH.relative_to(ROOT)
    activation_path = root / ACTIVATION_PATH.relative_to(ROOT)
    authorization = _load(authorization_path)
    authorization["next_action"] += " substituted"
    authorization_path.write_text(json.dumps(authorization, indent=2) + "\n", encoding="utf-8")
    activation = _load(activation_path)
    activation["authorization_identity"]["canonical_content_sha256"] = hashlib.sha256(
        authorization_path.read_bytes()
    ).hexdigest()
    activation_path.write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert any("canonical merge bytes mismatch" in issue for issue in projection["issues"])
    assert projection["active_project"] is None
