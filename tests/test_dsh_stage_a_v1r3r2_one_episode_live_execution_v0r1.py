from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r1"
)
ACTIVATION_PATH = ARTIFACT / "activation.json"
AUTHORIZATION_PATH = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r1/authorization.json"
)
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1"
HISTORICAL_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0"


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


def _synthetic_repo(tmp_path: Path, *, canonical: bool, state: str = "ACTIVE") -> tuple[Path, dict, dict]:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    _, _, registry = project_context.load_context_sources(ROOT)
    record = copy.deepcopy(next(item for item in registry["project"] if item["project_id"] == EXECUTION_ID))

    root = tmp_path / "repo"
    (root / "artifact").mkdir(parents=True)
    (root / "auth").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    base_sha = _commit(root, "base")

    canonical_sha = base_sha
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
    record["authorization_canonical_merge"] = canonical_sha
    record["canonical_predecessor_merge"] = canonical_sha
    record["state"] = state
    if state == "ACTIVE":
        record["implementation_authorized"] = True
        record["implementation_completed"] = False
        record["effective_execution_authority"] = True
    else:
        record["implementation_authorized"] = False
        record["implementation_completed"] = True
        record["terminal_outcome"] = "BLOCK_AUTHORITY"
        record["active_project_after_closure"] = "NONE"
        (root / "result").mkdir()
        (root / "result/execution_evidence.json").write_text("{}\n", encoding="utf-8")
        (root / "result/closure.md").write_text("terminal closure\n", encoding="utf-8")
        record["authoritative_artifacts"] += ["result/execution_evidence.json", "result/closure.md"]
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    candidate_sha = _commit(root, "activation candidate")
    if canonical:
        canonical_sha = candidate_sha
    subprocess.run(["git", "-C", str(root), "update-ref", "refs/remotes/origin/master", canonical_sha if canonical else base_sha], check=True)
    return root, activation, record


def test_fresh_activation_binds_authorization_runtime_episode_and_firewall() -> None:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    project = activation["active_execution_project"]
    assert activation["project_id"] == EXECUTION_ID
    assert activation["authorization_identity"]["project_id"] == AUTHORIZATION_ID
    assert activation["authorization_identity"]["candidate_commit"] == "f1c4313e4fccc721843883901af0ffc234d2d33a"
    assert activation["authorization_identity"]["canonical_merge"] == "afd5991abb2d3202367a22a5bda25526be476e69"
    assert activation["authorization_identity"]["project_id"] == authorization["project_id"]
    assert activation["episode_identity"]["episode_id"] == authorization["episode_authority"]["episode_id"]
    assert activation["episode_identity"]["episode_count"] == 1
    assert activation["claim_contract"]["remote_claim_ref"] == authorization["claim_contract"]["remote_claim_ref"]
    assert activation["claim_contract"]["remote_claim_exists"] is False
    assert activation["claim_contract"]["created_during_activation_construction"] is False
    assert project["state"] == "ACTIVE"
    assert project["implementation_authorized"] is True
    assert project["implementation_completed"] is False
    assert project["episode_consumed"] is False
    assert activation["runtime_identity"]["qualified_launch_contract_digest"] == authorization["qualified_launch_contract"]["digest"]
    assert activation["runtime_identity"]["runtime_manifest_digest"] == authorization["qualified_launch_contract"]["runtime_manifest_digest"]
    assert activation["runtime_identity"]["executable_identity_digest"] == authorization["qualified_launch_contract"]["executable_identity_digest"]
    assert activation["runtime_identity"]["launch_policy_digest"] == authorization["qualified_launch_contract"]["launch_policy_digest"]
    assert activation["claude_policy"]["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert activation["claude_policy"]["write_allowed"] is False
    assert activation["authority_firewall"] == {
        "stage_b_authorized": False,
        "qnty_runtime_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "scientific_execution_authorized": False,
        "promotion_authority": "NONE",
        "qnty_agent_eval": "NOT_APPLICABLE",
    }


def test_closed_execution_has_no_effective_authority_and_claim_is_untouched() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    identity = projection["identity_by_project"][EXECUTION_ID]
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert identity["effective"] is False
    assert identity["canonical_sha"] == "0f5d8d527ccbd0b284d8e9cc7dcd1bfe3518a278"
    assert identity["head_sha"] == identity["canonical_sha"]
    assert identity["candidate_base_is_ancestor"] is True


def test_historical_or_wrong_authorization_lineage_fails_closed(tmp_path: Path) -> None:
    root, activation, record = _synthetic_repo(tmp_path, canonical=True)
    activation["authorization_identity"]["project_id"] = HISTORICAL_AUTHORIZATION_ID
    record["authorization_project_id"] = HISTORICAL_AUTHORIZATION_ID
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("cannot substitute historical authorization" in issue for issue in projection["issues"])


def test_historical_pr183_active_registry_contradiction_fails_closed(tmp_path: Path) -> None:
    root, activation, record = _synthetic_repo(tmp_path, canonical=True, state="CLOSED_PASS")
    record["state"] = "CLOSED_PASS"
    record["implementation_authorized"] = False
    record["implementation_completed"] = True
    record["authoritative_artifacts"] = ["artifact/activation.json"]
    record["terminal_outcome"] = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_AUTHORIZATION_AVAILABLE"
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert projection["issues"]


def test_canonical_activation_projects_exactly_one_active_project(tmp_path: Path) -> None:
    root, _, record = _synthetic_repo(tmp_path, canonical=True)
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == EXECUTION_ID
    assert projection["active_project"]["implementation_authorized"] is True
    assert projection["active_project"]["implementation_completed"] is False
    assert projection["active_project"]["episode_consumed"] is False


def test_existing_claim_runtime_drift_and_firewall_mismatch_fail_closed(tmp_path: Path) -> None:
    root, activation, record = _synthetic_repo(tmp_path, canonical=True)
    activation["claim_contract"]["remote_claim_exists"] = True
    activation["runtime_identity"]["qualified_launch_contract_digest"] = "wrong"
    activation["parent_authority"]["max_total_spend_usd"] = 2.0
    activation["claude_policy"]["write_allowed"] = True
    activation["authority_firewall"]["stage_b_authorized"] = True
    record["stage_b_authorized"] = True
    record["spend_ceiling_usd"] = 2.0
    record["claude_write_allowed"] = True
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert any("existing claim state" in issue for issue in projection["issues"])
    assert any("qualified_launch_contract_digest" in issue for issue in projection["issues"])
    assert any("parent budget" in issue for issue in projection["issues"])
    assert any("Claude policy" in issue for issue in projection["issues"])
    assert any("downstream firewall" in issue for issue in projection["issues"])


def test_malformed_nested_authorization_fails_closed_without_projection_crash(tmp_path: Path) -> None:
    root, _, record = _synthetic_repo(tmp_path, canonical=True)
    authorization_path = root / "auth/authorization.json"
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["child_execution_policies"] = []
    authorization["qualified_launch_contract"]["repair_digests"] = []
    authorization["parent_authority"]["retry_policy"] = []
    authorization_path.write_text(json.dumps(authorization, indent=2) + "\n", encoding="utf-8")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["active_project"] is None
    assert projection["issues"]


def test_terminal_closure_removes_effective_execution_authority(tmp_path: Path) -> None:
    root, _, record = _synthetic_repo(tmp_path, canonical=True, state="CLOSED_BLOCKED")
    projection = project_context.execution_authority_projection(root, {EXECUTION_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"] is None
