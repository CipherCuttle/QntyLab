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
ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r3/activation.json"
AUTHORIZATION_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r3/authorization.json"
)
CONTRACT_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_launch_contract_requalification_v0/evidence/contract.json"
QUALIFICATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_launch_contract_requalification_v0/qualification.json"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R3"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r3"
E168 = "e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82"
LAUNCH_POLICY = "00336402a7b34757ba05194ae083805b84f699f1f706990278b9aaf121e973b4"
HISTORICAL_DIGESTS = {
    "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa",
    "c98c0a91d15c0875e3635e9791561af5bbb8588ff66d4144c822570b6227b666",
    "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1",
}


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=activation-test",
            "-c",
            "user.email=activation-test@example.invalid",
            "commit",
            "-qm",
            message,
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
    for source in (ACTIVATION_PATH, AUTHORIZATION_PATH, CONTRACT_PATH, QUALIFICATION_PATH):
        destination = root / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    base_sha = _commit(root, "base")

    activation_path = root / ACTIVATION_PATH.relative_to(ROOT)
    authorization_path = root / AUTHORIZATION_PATH.relative_to(ROOT)
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    authorization_identity = activation["authorization_identity"]
    activation["canonicalization"]["candidate_base_sha"] = base_sha
    activation["canonicalization"]["canonical_predecessor_merge"] = base_sha
    authorization_identity["candidate_commit"] = base_sha
    authorization_identity["canonical_merge"] = base_sha
    authorization_identity["canonical_content_sha256"] = hashlib.sha256(authorization_path.read_bytes()).hexdigest()
    authorization_identity["git_blob_sha"] = subprocess.run(
        ["git", "-C", str(root), "hash-object", str(authorization_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    activation_path.write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")

    record = _source_record()
    record["authoritative_artifacts"] = [str(ACTIVATION_PATH.relative_to(ROOT))]
    record["authorization_artifact"] = str(AUTHORIZATION_PATH.relative_to(ROOT))
    record["authorization_candidate_commit"] = base_sha
    record["authorization_canonical_merge"] = base_sha
    record["canonical_predecessor_merge"] = base_sha
    candidate_sha = _commit(root, "V0R3 activation candidate")
    canonical_sha = candidate_sha if canonical else base_sha
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/master", canonical_sha], check=True
    )
    return root, record


def test_activation_binds_v0r3_authorization_and_exact_contract() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
    assert activation["authorization_identity"]["project_id"] == AUTHORIZATION_ID
    assert activation["authorization_identity"]["canonical_merge"] == "a26b16b01090a67ae335533cabf752b0d7cb3df1"
    assert activation["authorization_identity"]["canonical_content_sha256"] == hashlib.sha256(AUTHORIZATION_PATH.read_bytes()).hexdigest()
    assert activation["authorization_identity"]["git_blob_sha"] == "4051f11e304b47d0f4e30843ec2845db1d15b0eb"
    assert activation["qualified_launch_contract"]["digest"] == E168 == contract["qualifiedContractDigest"]
    assert activation["qualified_launch_contract"]["launch_policy_digest"] == LAUNCH_POLICY
    assert activation["qualified_launch_contract"]["contract_artifact_sha256"] == hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert activation["qualified_launch_contract"]["qualification_artifact_sha256"] == hashlib.sha256(QUALIFICATION_PATH.read_bytes()).hexdigest()
    assert activation["qualified_launch_contract"]["qualification_artifact"]
    assert qualification["requalified_contract"]["qualified_digest"] == E168


def test_fresh_identity_is_one_unclaimed_unconsumed_v0r3_episode() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    project = activation["active_execution_project"]
    episode = activation["episode_identity"]
    assert activation["project_id"] == EXECUTION_ID
    assert episode == {
        "execution_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "episode_generation": "V0R3",
        "episode_count": 1,
        "episode_claimed": False,
        "episode_consumed": False,
        "claim_ref": CLAIM_REF,
    }
    assert project["authorized_live_episodes"] == 1
    assert project["second_episode_authorized"] is False
    assert project["whole_episode_retry_allowed"] is False
    assert project["activation_consumes_live_episode"] is False


def test_claim_preflight_is_absent_and_activation_creates_no_claim() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    claim = activation["claim_contract"]
    state_dir = Path(claim["local_receipt_state_dir"])
    assert subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", CLAIM_REF], capture_output=True, text=True
    ).returncode != 0
    assert not state_dir.exists()
    assert claim["remote_claim_exists"] is False
    assert claim["local_claim_exists"] is False
    assert claim["created_during_activation_construction"] is False
    assert claim["mode"] == "CREATE_ONLY_AT_MOST_ONCE_NO_OVERWRITE_NO_REPLAY_NO_REUSE"
    assert activation["construction_receipts"]["claims_created"] == 0


def test_branch_candidate_is_ineffective_and_canonical_candidate_has_one_active_project(tmp_path: Path) -> None:
    candidate_root, candidate_record = _synthetic_repo(tmp_path, canonical=False)
    candidate = project_context.execution_authority_projection(candidate_root, {EXECUTION_ID: candidate_record})
    assert candidate["issues"] == []
    assert candidate["active_project"] is None
    assert candidate["identity_by_project"][EXECUTION_ID]["effective"] is False

    canonical_root, canonical_record = _synthetic_repo(tmp_path, canonical=True)
    projection = project_context.execution_authority_projection(canonical_root, {EXECUTION_ID: canonical_record})
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == EXECUTION_ID
    assert projection["active_project"]["episode_consumed"] is False
    assert len([projection["active_project"]]) == 1


def test_wrong_authorization_contract_policy_or_activation_bytes_fail_closed(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, canonical=True)
    activation_path = root / ACTIVATION_PATH.relative_to(ROOT)
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    activation["authorization_identity"]["project_id"] = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2"
    activation["qualified_launch_contract"]["digest"] = next(iter(HISTORICAL_DIGESTS))
    activation["runtime_identity"]["launch_policy_digest"] = next(iter(HISTORICAL_DIGESTS))
    activation_path.write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert projection["issues"]

    root, record = _synthetic_repo(tmp_path, canonical=True)
    activation_path = root / ACTIVATION_PATH.relative_to(ROOT)
    activation_path.write_text(activation_path.read_text(encoding="utf-8").replace("ACTIVE_CANDIDATE", "DRIFTED"), encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert projection["identity_by_project"][EXECUTION_ID]["effective"] is False


def test_historical_lineages_pr189_and_claim_substitution_are_rejected(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, canonical=True)
    activation_path = root / ACTIVATION_PATH.relative_to(ROOT)
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    activation["authorization_identity"]["project_id"] = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0"
    activation["episode_identity"]["claim_ref"] = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2r1"
    record["authorization_project_id"] = activation["authorization_identity"]["project_id"]
    record["claim_ref"] = activation["episode_identity"]["claim_ref"]
    activation_path.write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("historical" in issue or "claim" in issue for issue in projection["issues"])
    assert "PR #189" not in activation["authorization_identity"]["project_id"]
    assert activation["authorization_identity"]["historical_authorization_rejected"]


def test_parent_budget_child_machine_and_hard_read_only_policy_are_exact() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    parent = activation["parent_authority"]
    assert (parent["provider"], parent["model"], parent["route"]) == ("openai", "gpt-5-mini", "llm-pi-ai")
    assert parent["max_request_attempts"] == 8
    assert parent["provider_internal_retries"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["max_output_tokens_per_request"] == 4096
    assert activation["spend_authority"]["cap_usd"] == "1.00"
    assert activation["spend_authority"]["hard_cap"] is True
    child = activation["child_authority"]
    assert child["codex_calls_max"] == 2
    assert child["claude_calls_max"] == 2
    assert child["generic_child_tools"] == []
    assert child["alternate_delegation_routes"] == []
    assert child["background_delegation"] is False
    assert activation["codex_policy"]["route"] == "codex app-server --stdio"
    assert activation["codex_policy"]["workspace_write_scope"] == "disposable Stage-A fixture workspace only"
    claude = activation["claude_policy"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert claude["write_allowed"] is False
    assert claude["edit_allowed"] is False
    assert claude["bash_allowed"] is False
    assert claude["agent_allowed"] is False
    assert claude["task_allowed"] is False
    assert claude["mcp_allowed"] is False
    assert claude["setting_sources"] == []
    assert claude["mcp_servers"] == {}
    assert claude["plugins"] == []
    assert claude["persistence"] is False


def test_fixture_workspace_secret_order_timeout_and_firewall_are_closed() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    fixture = activation["fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["fixture_digest"] == "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"
    assert fixture["mutable_paths"] == ["retry.py"]
    assert fixture["immutable_paths"] == ["TASK.md", "tests/test_retry.py"]
    assert fixture["canonical_fixture_mutation_allowed"] is False
    workspace = activation["workspace_policy"]
    assert workspace["fresh_disposable_workspace_required"] is True
    assert workspace["fresh_disposable_dsh_home_required"] is True
    assert workspace["fresh_disposable_fixture_copy_required"] is True
    assert workspace["realpath_symlink_aware_containment_required"] is True
    assert "QntyLab" in workspace["forbidden_write_roots"]
    assert "~/.codex" in workspace["forbidden_write_roots"]
    order = activation["canonical_gate_order"]
    assert order.index("secret read/availability gate") > order.index("parent/child budget verification")
    assert order.index("secret read/availability gate") < order.index("if secret succeeds: create claim")
    assert order.index("if secret succeeds: create claim") < order.index("only after complete claim: first potentially paid parent dispatch")
    assert activation["secret_binding_contract"]["authorization_phase_secret_reads"] == 0
    timeout = activation["timeout_policy"]
    assert timeout["live_episode_timeout_seconds"] == 1800
    assert timeout["timeout_allows_rerun"] is False
    assert timeout["terminal_failure_allows_rerun"] is False
    assert timeout["claim_crossed_timeout_or_crash_behavior"] == "BLOCK_NEVER_REPLAY"
    firewall = activation["authority_firewall"]
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
    assert firewall["broader_production_authority"] == "NONE"


def test_activation_phase_has_zero_external_activity_and_no_fixture_mutation() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    receipts = activation["construction_receipts"]
    assert receipts["real_secret_reads"] == 0
    assert receipts["claims_created"] == 0
    assert receipts["live_dsh_calls"] == 0
    assert receipts["external_provider_requests"] == 0
    assert receipts["real_codex_child_turns"] == 0
    assert receipts["real_claude_child_turns"] == 0
    assert receipts["fixture_mutations"] == 0
    assert receipts["spend_usd"] == "0"
    status = activation["execution_status"]
    assert status["episode_started"] is False
    assert status["episode_claimed"] is False
    assert status["episode_consumed"] is False
    assert status["dsh_invocations"] == 0
    assert status["external_provider_requests"] == 0
    assert status["fixture_mutations"] == 0


def test_project_context_registry_projection_is_fail_closed_for_v0r3() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    v0r3 = projects[EXECUTION_ID]
    assert v0r3["state"] == "ACTIVE"
    assert v0r3["implementation_authorized"] is True
    assert v0r3["episode_claimed"] is False
    assert v0r3["episode_consumed"] is False
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert projection["identity_by_project"][EXECUTION_ID]["effective"] is False


def test_project_context_mismatch_cannot_activate_v0r3(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, canonical=True)
    record["launch_policy_digest"] = "wrong"
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("launch_policy_digest" in issue for issue in projection["issues"])
