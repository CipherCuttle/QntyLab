from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ARTIFACT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r2r1"
ACTIVATION_PATH = ARTIFACT / "activation.json"
AUTHORIZATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r2r1/authorization.json"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1"
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2R1"
OLD_AUTHORIZATION_IDS = {
    "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0",
    "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1",
    "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2",
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


def _synthetic_repo(tmp_path: Path, *, canonical: bool, closed: bool = False) -> tuple[Path, dict, dict]:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    _, _, registry = project_context.load_context_sources(ROOT)
    record = copy.deepcopy(next(item for item in registry["project"] if item["project_id"] == EXECUTION_ID))

    root = tmp_path / ("canonical" if canonical else "candidate")
    (root / "artifact").mkdir(parents=True)
    (root / "auth").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    base_sha = _commit(root, "base")

    activation["canonicalization"]["candidate_base_sha"] = base_sha
    activation["canonicalization"]["canonical_predecessor_merge"] = base_sha
    activation["authorization_identity"]["candidate_commit"] = base_sha
    activation["authorization_identity"]["canonical_merge"] = base_sha
    activation["authorization_identity"]["artifact"] = "auth/authorization.json"
    authorization["canonicalization"]["candidate_base_sha"] = base_sha
    (root / "auth/authorization.json").write_text(json.dumps(authorization, indent=2) + "\n", encoding="utf-8")

    record["authoritative_artifacts"] = ["artifact/activation.json"]
    record["authorization_artifact"] = "auth/authorization.json"
    record["authorization_candidate_commit"] = base_sha
    record["authorization_canonical_merge"] = base_sha
    record["canonical_predecessor_merge"] = base_sha
    if closed:
        record["state"] = "CLOSED_BLOCKED"
        record["implementation_authorized"] = False
        record["implementation_completed"] = True
        record["effective_execution_authority"] = False
        record["terminal_outcome"] = "BLOCK_AUTHORITY"
        record["active_project_after_closure"] = "NONE"
        (root / "result").mkdir()
        (root / "result/execution_evidence.json").write_text("{}\n", encoding="utf-8")
        (root / "result/closure.md").write_text("terminal closure\n", encoding="utf-8")
        record["authoritative_artifacts"] += ["result/execution_evidence.json", "result/closure.md"]
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    candidate_sha = _commit(root, "activation candidate")
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/master", candidate_sha if canonical else base_sha],
        check=True,
    )
    return root, activation, record


def test_activation_binds_canonical_authorization_and_one_episode_contract() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    project = activation["active_execution_project"]

    assert activation["project_id"] == EXECUTION_ID
    assert activation["authorization_identity"] == {
        "project_id": AUTHORIZATION_ID,
        "candidate_commit": "3c2be8acc83efce1cd518bcdf03b7d41b0fb4829",
        "canonical_merge": "c60cbc772de45ca6caa27a5ee651b9599831df1a",
        "required_state": "CLOSED_PASS",
        "artifact": authorization["canonicalization"]["candidate_artifact_path"],
        "historical_authorization_rejected": sorted(OLD_AUTHORIZATION_IDS),
        "historical_execution_rejected": [
            "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0",
            "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1",
            "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2",
        ],
    }
    assert project == {
        "state": "ACTIVE",
        "authority_level": "BOUNDED_ONE_EPISODE_DSH_STAGE_A_LIVE_EXECUTION_ONLY",
        "phase_type": "BOUNDED_LIVE_INFRASTRUCTURE_EXECUTION",
        "implementation_authorized": True,
        "implementation_completed": False,
        "episode_claimed": False,
        "episode_consumed": False,
        "authorized_live_episodes": 1,
        "second_episode_authorized": False,
        "whole_episode_retry_allowed": False,
        "execution_closure_pr_budget": 1,
        "activation_consumes_live_episode": False,
        "activation_consumes_execution_closure_pr_budget": False,
    }
    assert activation["runtime_identity"]["qualified_launch_contract_digest"] == "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa"
    assert activation["runtime_identity"]["runtime_manifest_digest"] == "afcfa011de46bd9fccaa120b5612c24a5ace2b2c451591ddf8b67fb43a8ce321"
    assert activation["runtime_identity"]["executable_identity_digest"] == "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
    assert activation["runtime_identity"]["launch_policy_digest"] == "024256a6dd2fbce6e883a73d9d2df01e3b2b21f738c7ca700c86cca13bd1ec73"
    assert activation["runtime_identity"]["superseded_digest_rejected"] == "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
    assert activation["canonical_enforcement_bytes"] == authorization["canonical_enforcement_bytes"]


def test_claim_profile_secret_and_downstream_firewall_are_closed_at_activation() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    claim = activation["claim_contract"]
    assert claim["remote"] == "https://github.com/CipherCuttle/QntyLab.git"
    assert claim["remote_claim_ref"] == "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2r1"
    assert claim["local_receipt_state_dir"] == "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2r1/episode-1"
    assert claim["remote_claim_exists"] is False
    assert claim["local_claim_exists"] is False
    assert claim["created_during_activation_construction"] is False
    assert activation["episode_identity"]["episode_count"] == 1
    assert activation["episode_identity"]["episode_claimed"] is False
    assert activation["episode_identity"]["episode_consumed"] is False
    assert activation["active_execution_project"]["second_episode_authorized"] is False
    assert activation["active_execution_project"]["whole_episode_retry_allowed"] is False
    assert activation["profile_contract"]["live_profile"] == "PRODUCTION"
    assert activation["profile_contract"]["offline_qualification_patch_allowed_for_live"] is False
    assert activation["parent_authority"]["provider_internal_retries"] == 0
    assert activation["parent_authority"]["max_request_attempts"] == 8
    assert activation["parent_authority"]["max_output_tokens_per_request"] == 4096
    assert activation["spend_authority"]["scope"] == "PARENT_OPENAI_AUTHORIZED_SPEND_USD_UNDER_FROZEN_SCHEDULE"
    assert activation["spend_authority"]["cap_usd"] == "1.00"
    assert activation["child_authority"]["codex_calls_max"] == 2
    assert activation["child_authority"]["claude_calls_max"] == 2
    assert activation["claude_policy"]["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert activation["claude_policy"]["write_allowed"] is False
    assert activation["secret_binding_contract"]["source_path"] == "~/.secrets/openai_api_key_stage_a"
    assert activation["secret_binding_contract"]["authorization_phase_secret_read"] is False
    assert activation["construction_receipts"] == {
        "activation_artifacts_created": 1,
        "claim_creations": 0,
        "external_provider_requests": 0,
        "fixture_mutations": 0,
        "live_dsh_calls": 0,
        "real_claude_child_turns": 0,
        "real_codex_child_turns": 0,
        "real_secret_reads": 0,
        "spend_usd": "0",
    }
    assert activation["authority_firewall"] == {
        "stage_b_authorized": False,
        "qnty_runtime_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "scientific_execution_authorized": False,
        "promotion_authority": "NONE",
        "qnty_agent_eval": "NOT_APPLICABLE",
    }


def test_candidate_activation_is_ineffective_and_canonical_activation_projects_one_active_project(tmp_path: Path) -> None:
    candidate_root, _, candidate_record = _synthetic_repo(tmp_path, canonical=False)
    candidate_projection = project_context.execution_authority_projection(candidate_root, {EXECUTION_ID: candidate_record})
    assert candidate_projection["issues"] == []
    assert candidate_projection["active_project"] is None
    assert candidate_projection["identity_by_project"][EXECUTION_ID]["effective"] is False

    canonical_root, _, canonical_record = _synthetic_repo(tmp_path, canonical=True)
    canonical_projection = project_context.execution_authority_projection(canonical_root, {EXECUTION_ID: canonical_record})
    assert canonical_projection["issues"] == []
    assert canonical_projection["active_project"]["project_id"] == EXECUTION_ID
    assert canonical_projection["active_project"]["implementation_authorized"] is True
    assert canonical_projection["active_project"]["implementation_completed"] is False
    assert canonical_projection["active_project"]["episode_consumed"] is False


def test_canonical_registry_contains_exactly_one_current_active_execution_row() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    active = [record["project_id"] for record in projects.values() if record["state"] == "ACTIVE"]
    assert active == [EXECUTION_ID]
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert projection["identity_by_project"][EXECUTION_ID]["canonical_sha"] == "c60cbc772de45ca6caa27a5ee651b9599831df1a"
    assert projection["identity_by_project"][EXECUTION_ID]["effective"] is False


def test_historical_authorization_and_wrong_claim_lineage_fail_closed(tmp_path: Path) -> None:
    root, activation, record = _synthetic_repo(tmp_path, canonical=True)
    activation["authorization_identity"]["project_id"] = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2"
    record["authorization_project_id"] = activation["authorization_identity"]["project_id"]
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("cannot substitute historical authorization" in issue for issue in projection["issues"])

    activation["authorization_identity"]["project_id"] = AUTHORIZATION_ID
    activation["episode_identity"]["claim_ref"] = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2"
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("claim" in issue for issue in projection["issues"])


def test_existing_claim_old_digest_offline_profile_and_firewall_drift_fail_closed(tmp_path: Path) -> None:
    root, activation, record = _synthetic_repo(tmp_path, canonical=True)
    activation["claim_contract"]["remote_claim_exists"] = True
    activation["runtime_identity"]["qualified_launch_contract_digest"] = "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
    activation["profile_contract"]["offline_qualification_patch_allowed_for_live"] = True
    activation["parent_authority"]["max_total_spend_usd"] = 2.0
    activation["claude_policy"]["write_allowed"] = True
    activation["authority_firewall"]["stage_b_authorized"] = True
    record["stage_b_authorized"] = True
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("existing claim state" in issue for issue in projection["issues"])
    assert any("qualified_launch_contract_digest" in issue for issue in projection["issues"])
    assert any("profile_contract" in issue for issue in projection["issues"])
    assert any("parent budget" in issue for issue in projection["issues"])
    assert any("Claude policy" in issue for issue in projection["issues"])
    assert any("downstream firewall" in issue for issue in projection["issues"])


def test_terminal_closure_removes_effective_execution_authority(tmp_path: Path) -> None:
    root, _, record = _synthetic_repo(tmp_path, canonical=True, closed=True)
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"] is None
