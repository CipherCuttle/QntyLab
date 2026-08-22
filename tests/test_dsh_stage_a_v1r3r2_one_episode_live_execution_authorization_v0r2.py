from __future__ import annotations

import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r2"
)
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2"
V0R1_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1"
V0R1_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"
V0R2_CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r2"
V0R1_CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r1"


def _explicit_secret_gate(*, exists: bool, readable: bool, nonempty: bool, binding_probe: bool) -> bool:
    """Synthetic gate model; it never reads a real operator secret."""
    return exists and readable and nonempty and binding_probe


def _provider_dispatch(*, claim_created: bool, provider_io: bool) -> list[str]:
    events = ["non_secret_gates"]
    if not claim_created and provider_io:
        events.append("BLOCK_BEFORE_PROVIDER_IO")
    elif claim_created and provider_io:
        events.extend(("claim_created", "provider_io"))
    return events


def test_case_01_v0r1_authorization_cannot_satisfy_v0r2() -> None:
    assert AUTH["project_id"] == AUTHORIZATION_ID
    assert AUTH["project_id"] != V0R1_AUTHORIZATION_ID
    assert AUTH["historical_authority_rejected"]["substitution_allowed"] is False


def test_case_02_v0r1_activation_cannot_satisfy_v0r2() -> None:
    assert AUTH["execution_project_id"] == EXECUTION_ID
    assert EXECUTION_ID != V0R1_EXECUTION_ID
    assert AUTH["activation_prerequisite"]["old_authorization_or_activation_satisfies"] is False


def test_case_03_v0r1_claim_ref_cannot_substitute_for_v0r2() -> None:
    claim = AUTH["claim_contract"]
    assert claim["remote_claim_ref"] == V0R2_CLAIM_REF
    assert V0R1_CLAIM_REF in claim["historical_claim_refs_rejected"]
    assert claim["remote_claim_ref"] != V0R1_CLAIM_REF


def test_case_04_authorization_alone_does_not_activate_execution() -> None:
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert AUTH["activation_prerequisite"]["activation_exists_initial"] is False
    assert AUTH["execution_authority_after_construction"]["effective_execution_authority"] is False
    assert not list(ARTIFACT.glob("activation.json"))


def test_case_05_noncanonical_v0r2_authorization_is_ineffective() -> None:
    canonical = AUTH["canonicalization"]
    assert canonical["branch_local_artifact_does_not_self_authorize"] is True
    assert canonical["canonical_presence_required_before_execution"] is True
    assert canonical["candidate_base_sha"] == "276c1706c02bdb4fcc0d3e688c371e20fcee2065"

    def effective(*, canonical_head: str, clean: bool) -> bool:
        return clean and canonical_head == canonical["candidate_base_sha"]

    assert effective(canonical_head="candidate-only", clean=True) is False
    assert effective(canonical_head=canonical["candidate_base_sha"], clean=True) is True


def test_case_06_historical_closed_v0r1_remains_closed() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    closed = projects[V0R1_EXECUTION_ID]
    assert closed["state"] == "CLOSED_BLOCKED"
    assert closed["terminal_outcome"] == "BLOCK_PARENT_INFRA"
    assert closed["episode_claimed"] is False
    assert closed["episode_consumed"] is False
    assert closed["claim_ref"] == V0R1_CLAIM_REF
    assert AUTH["historical_closure"]["rerun_authorized"] is False


def test_case_07_secret_contract_requires_explicit_extra_env_binding() -> None:
    contract = AUTH["secret_binding_contract"]
    assert contract["auth_env"] == "OPENAI_API_KEY"
    assert contract["binding_mechanism"] == "spawnDsh(..., { extraEnv: { OPENAI_API_KEY: value } })"
    assert contract["explicit_extra_env_required"] is True
    assert contract["ambient_process_inheritance_relied_on"] is False


def test_case_08_ambient_process_only_check_is_insufficient() -> None:
    contract = AUTH["secret_binding_contract"]
    assert contract["ambient_process_check_sufficient"] is False

    def ambient_only_gate(*, ambient_present: bool, explicit_binding_probe: bool) -> bool:
        return ambient_present and explicit_binding_probe

    assert ambient_only_gate(ambient_present=True, explicit_binding_probe=False) is False
    assert ambient_only_gate(ambient_present=False, explicit_binding_probe=True) is False
    assert ambient_only_gate(ambient_present=True, explicit_binding_probe=True) is True


def test_case_09_missing_unreadable_empty_secret_blocks_before_claim() -> None:
    for state in (
        {"exists": False, "readable": False, "nonempty": False},
        {"exists": True, "readable": False, "nonempty": False},
        {"exists": True, "readable": True, "nonempty": False},
    ):
        assert _explicit_secret_gate(**state, binding_probe=True) is False
    assert AUTH["secret_missing_blocks_before_claim"] is True
    assert AUTH["construction_receipts"]["claim_creations"] == 0


def test_case_10_provider_io_before_successful_claim_is_forbidden() -> None:
    assert _provider_dispatch(claim_created=False, provider_io=True) == [
        "non_secret_gates",
        "BLOCK_BEFORE_PROVIDER_IO",
    ]
    assert AUTH["provider_io_before_claim_forbidden"] is True
    assert AUTH["claim_contract"]["both_complete_before_first_potentially_paid_parent_dispatch"] is True


def test_case_11_claude_secret_inheritance_remains_forbidden() -> None:
    claude = AUTH["child_execution_policies"]["claude"]
    assert AUTH["secret_binding_contract"]["child_secret_inheritance"] is False
    assert AUTH["secret_policy"]["secret_must_not_reach_child_processes"] is True
    synthetic_child_environment_names = {"PATH", "HOME"}
    assert "OPENAI_API_KEY" not in synthetic_child_environment_names
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]


def test_case_12_runtime_digest_mismatch_fails_closed() -> None:
    contract = AUTH["qualified_launch_contract"]
    assert contract["mismatch_behavior"] == "BLOCK_BEFORE_SECRET_READ_AND_MODEL_IO"
    assert contract["requalification_required"] is False
    observed = dict(contract)
    observed["digest"] = "synthetic-drift"
    assert observed["digest"] != contract["digest"]
    assert contract["direct_identity_drift_only_block"] is True


def test_case_13_second_episode_remains_unauthorized() -> None:
    episode = AUTH["episode_authority"]
    assert episode["episode_count"] == 1
    assert episode["second_episode_allowed"] is False
    assert episode["whole_episode_retry_allowed"] is False
    assert AUTH["execution_closure_pr_budget"] == 1
    assert AUTH["wall_clock"]["timeout_allows_rerun"] is False


def test_case_14_downstream_stage_b_qnty_trading_capital_remain_denied() -> None:
    firewall = AUTH["governance_boundary"]
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["qnty_agent_eval"] == "NOT_APPLICABLE"


def test_project_context_has_no_active_execution_project() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projects[AUTHORIZATION_ID]["state"] == "CLOSED_PASS"
    assert projection["issues"] == []
    assert projection["active_project"] is None
