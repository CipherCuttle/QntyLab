import hashlib
import json
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/stage_a_zero_write_authorization_v0/authorization.json"
REGISTRATION = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/ecosystem_registration_v0r1/registration.json"
PROJECTS = ROOT / "docs/state/projects.toml"


def test_zero_write_decision_is_derived_without_reopening_history() -> None:
    artifact = json.loads(AUTH.read_text(encoding="utf-8"))
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    projects = tomllib.loads(PROJECTS.read_text(encoding="utf-8"))
    project = next(item for item in projects["project"] if item["project_id"] == artifact["project_id"])

    assert artifact["state"] == "CLOSED_PASS"
    assert artifact["phase_type"] == "GOVERNANCE_ONLY"
    assert artifact["canonicalization"]["canonical_master_sha"] == "34628822d2c83fcc647d9021fc687acc5aeaacf7"
    assert artifact["canonicalization"]["source_conflict"] is False
    assert artifact["canonicalization"]["historical_registration_reopened"] is False
    assert artifact["canonicalization"]["historical_registration_rewritten"] is False
    assert artifact["historical_provenance"]["previous_registration_classification"] == "PRESERVED_HISTORICAL_FACT"
    assert artifact["historical_provenance"]["previous_stage_a_blocker"] is True
    assert hashlib.sha256(REGISTRATION.read_bytes()).hexdigest() == artifact["historical_provenance"]["previous_registration_sha256"]
    assert registration["branch_protection"]["stage_a_blocker"] is True

    scope = artifact["stage_a_scope"]
    assert scope["stage_a_github_writes"] == 0
    assert scope["stage_a_github_write_credentials"] == "NONE"
    assert scope["stage_a_pr_publication"] == scope["stage_a_merge"] == "NO"
    assert scope["stage_a_runtime_implementation"] == "NO"
    assert scope["stage_a_dsh_execution_in_this_authorization_phase"] == "NO"
    assert scope["trusted_git_broker_invoked"] is False
    assert artifact["derived_decision"] == {
        "branch_protection_required_for_zero_write_stage_a": "NO",
        "branch_protection_required_for_trusted_git_publication": "YES",
        "branch_protection_required_for_higher_autonomy": "YES",
        "causal_basis": artifact["derived_decision"]["causal_basis"],
    }

    firewall = artifact["authority_firewall"]
    assert firewall["runtime_implementation_authorized"] is False
    assert firewall["dsh_implementation_authorized"] is False
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["qnty_next_action_authority"] == "NONE"
    assert firewall["trading_authority"] == firewall["capital_authority"] == "NONE"
    assert firewall["auto_merge_authorized"] is False
    assert firewall["current_max_autonomy"] == "L0_SHADOW"
    assert firewall["second_authority_plane_created"] is False

    assert project["state"] == "CLOSED_PASS"
    assert project["implementation_authorized"] is False
    assert project["phase_type"] == "GOVERNANCE_ONLY"
    assert project["hostile_review_count"] == 1
    assert project["hostile_governance_critical_total"] == 0
    assert project["hostile_governance_high_total"] == 0


def test_protected_paths_are_absent_from_phase_diff() -> None:
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", "34628822d2c83fcc647d9021fc687acc5aeaacf7", "--"],
            cwd=ROOT,
            text=True,
        ).splitlines()
    )
    assert not {"docs/ADR/0005-qntylab-north-star-market-intelligence-architecture.md", "docs/ADR/0007-ecosystem-role-boundary-and-context-spine-governance.md", "docs/ADR/0008-qnty-agent-orchestration-runtime-boundary.md"} & changed
    assert not {"docs/state/ecosystem.toml"} & changed
    assert not any("order_flow" in path.lower() or "order-flow" in path.lower() for path in changed)
    assert not any("qntyagent" in path.lower() or "qnty_agent_eval" in path.lower() or "qntypolicygate" in path.lower() for path in changed)
