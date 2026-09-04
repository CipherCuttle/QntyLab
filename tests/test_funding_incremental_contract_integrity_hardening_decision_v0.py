import hashlib
import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "contract_integrity_hardening_decision_v0/decision.json"
)
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
ROADMAP_PATH = ROOT / "docs/CURRENT_ROADMAP.md"
EXECUTOR_V0_PATH = ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
REAL_CAPABLE_WRAPPER_V1_PATH = ROOT / (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1.py"
)
PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_DECISION_V0"
PHASE_ID = "FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_DECISION_V0"
LATER_PHASE = "FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0"
EXECUTOR_V0_SHA256 = "1ffcfeb959cfc547fcda96384c1c8f58b3f5cbc174c5d535324480ede312e8c6"
REAL_CAPABLE_WRAPPER_V1_SHA256 = "b0d30af9f6def297c23981c554d6c2224ff1736a491db009a9d8ce7fcc9a9b2e"
MANDATED_INVARIANTS = (
    "PROVENANCE_CONSTRUCTOR_HONESTY",
    "EXECUTION_MODE_IS_NOT_PROVENANCE",
    "PRIVATE_EXECUTION_SEAM_FORBIDDEN",
    "AUTHORITY_FAILURE_PRECEDES_ROWS",
    "EXACTLY_ONCE_PROCESS_BOUNDARY",
    "EXACTLY_ONCE_SECOND_WORKER",
    "CONFLICTING_REPLAY_FAILS_CLOSED",
    "RESULT_RECORD_IS_DURABLE",
    "FROZEN_V0_BYTES_UNCHANGED",
)


def _decision() -> dict[str, object]:
    return json.loads(DECISION_PATH.read_text(encoding="utf-8"))


def _record(project_id: str) -> dict[str, object]:
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == project_id)


def test_decision_identity_and_open_review_state() -> None:
    decision = _decision()
    record = _record(PROJECT_ID)

    assert record["phase_id"] == decision["phase_id"] == PHASE_ID
    assert record["project_id"] == decision["project_id"] == PROJECT_ID
    assert record["phase_type"] == decision["phase_type"] == "GOVERNANCE_ONLY"
    assert record["governance_only"] is True
    assert decision["governance_only"] is True
    assert decision["state"] == "CLOSED_PASS"
    assert decision["decision_state"] == decision["state"]
    assert decision["authority"] == "CANONICAL_QNTYLAB_GIT_IDENTITY_GOVERNANCE_ONLY"
    assert DECISION_PATH.is_file()
    assert decision["canonical_parent"] == "74e6edd0bbb51b98f92eb0c5ece881599e0f7d05"
    assert decision["forensic_audit_commit"] == decision["canonical_parent"]
    assert decision["forensic_audit_identity"] == "QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"


def test_decision_grants_exactly_one_non_scientific_implementation_phase() -> None:
    decision = _decision()

    assert decision["later_implementation_phase_count"] == 1
    assert decision["scientific_evaluation_phase_count"] == 0
    assert decision["authorization_count"]["later_implementation_phases_authorized"] == 1
    assert decision["authorization_count"]["scientific_evaluation_phases_authorized"] == 0
    assert decision["authorized_later_implementation_phase"] == LATER_PHASE


def test_decision_authorizes_no_access_and_no_authority() -> None:
    decision = _decision()

    assert decision["real_data_access_authorized"] is False
    assert decision["outcome_access_authorized"] is False
    assert decision["provider_access_authorized"] is False
    assert decision["claim_consumption_authorized"] is False
    assert decision["scientific_execution_authorized"] is False
    assert decision["router_authority"] == "NONE"
    assert decision["qnty_authority"] == "NONE"
    assert decision["qntyspot_authority"] == "NONE"
    assert decision["trading_authority"] == "NONE"
    assert decision["capital_authority"] == "NONE"


def test_selected_architecture_and_pr241_policy() -> None:
    decision = _decision()

    assert decision["selected_architecture"] == "OPTION_B_PRESERVE_FROZEN_V0_ORACLE_VERSIONED_HARDENED_SUCCESSOR"
    assert decision["verdict"] == (
        "ONE_FROZEN_ORACLE_PRESERVING_VERSIONED_HARDENED_SUCCESSOR_BOUNDARY_IS_AUTHORIZED"
        "_FOR_EXACTLY_ONE_NON_SCIENTIFIC_IMPLEMENTATION_PHASE"
    )
    pr241 = decision["pr241_policy"]
    assert pr241["merge_authority"] == "NONE"
    assert pr241["repair_authority"] == "NONE"
    assert pr241["rereview_authority"] == "NONE"
    assert pr241["cherrypick_whole_commit_authority"] == "NONE"
    assert pr241["candidate_commit"] == "d181d12096e19c1dbe2f89585e73b8f8f7b6b21f"
    assert pr241["ancestor_of_master"] is False


def test_forensic_findings_and_frozen_policy_hashes() -> None:
    decision = _decision()

    for finding in ("CI-1", "CI-23", "CI-11", "CI-7"):
        assert finding in decision["forensic_finding_ids"]
    assert decision["forensic_finding_ids"] == ["CI-1", "CI-2", "CI-7", "CI-10", "CI-11", "CI-23"]
    assert decision["forensic_evidence"]["CI-1"]["reachability"] == "LATENT_ON_MASTER"
    assert decision["forensic_evidence"]["CI-10"]["reachability"] == "BRANCH_ONLY"
    assert decision["forensic_evidence"]["CI-23"]["reachability"] == "BRANCH_ONLY"

    frozen = decision["frozen_v0_policy"]
    assert frozen["executor_v0_mutable"] is False
    # Live hashes double as pre-implementation freeze enforcement.
    assert hashlib.sha256(EXECUTOR_V0_PATH.read_bytes()).hexdigest() == EXECUTOR_V0_SHA256
    assert frozen["sha256"] == EXECUTOR_V0_SHA256
    exception = frozen["frozen_exception_modules"][0]
    assert hashlib.sha256(REAL_CAPABLE_WRAPPER_V1_PATH.read_bytes()).hexdigest() == REAL_CAPABLE_WRAPPER_V1_SHA256
    assert exception["sha256"] == REAL_CAPABLE_WRAPPER_V1_SHA256
    assert exception["disposition"] == "HISTORICAL_FAIL_CLOSED_FROZEN"


def test_required_invariants_present_and_required() -> None:
    decision = _decision()
    invariants = decision["required_invariants"]

    for name in MANDATED_INVARIANTS:
        assert name in invariants
        assert invariants[name]["required"] is True
    assert all(entry["required"] is True for entry in invariants.values())
    assert "NO_PROCESS_LOCAL_PERSISTENCE_STATE" in invariants
    assert "RESULT_RECORDING_PROSE_MATCHES_BEHAVIOR" in invariants
    assert "AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE" in invariants


def test_kill_criteria_and_non_authorizations_scope() -> None:
    decision = _decision()

    assert decision["kill_criteria"]
    non_auths = " ".join(decision["explicit_non_authorizations"])
    assert "pyproject.toml" in non_auths
    assert "P3 deletions" in non_auths
    assert decision["authorized_implementation_surfaces"]["forbidden"]
    assert "executor_v0" in decision["authorized_implementation_surfaces"]["forbidden"]


def test_registry_record_mirrors_decision_and_roadmap_renders() -> None:
    decision = _decision()
    record = _record(PROJECT_ID)

    assert record["decision_artifact"] == (
        "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
        "contract_integrity_hardening_decision_v0/decision.json"
    )
    assert record["decision_state"] == decision["decision_state"] == "CLOSED_PASS"
    assert record["state"] == "CLOSED_PASS"
    # F-003 repair: the registry sha256 pin must match the live decision artifact bytes.
    live_decision_sha256 = hashlib.sha256(DECISION_PATH.read_bytes()).hexdigest()
    assert live_decision_sha256 == record["decision_artifact_sha256"]
    assert record["candidate_state"] == "CANONICAL_GOVERNANCE_DECISION"
    assert record["phase_type"] == "GOVERNANCE_ONLY"
    assert record["governance_only"] is True
    assert record["later_implementation_phase"] == LATER_PHASE
    assert record["later_implementation_phases_authorized"] == 1
    assert record["scientific_evaluation_phases_authorized"] == 0
    assert record["scientific_execution_authorized"] is False
    assert record["real_data_access_authorized"] is False
    assert record["outcome_access_authorized"] is False
    assert record["provider_access_authorized"] is False
    assert record["claim_access_authorized"] is False
    assert record["implementation_authorized"] is False
    assert record["router_authority"] == "NONE"
    assert record["qnty_authority"] == "NONE"
    assert record["qntyspot_authority"] == "NONE"
    assert record["trading_authority"] == "NONE"
    assert record["capital_authority"] == "NONE"
    assert "Funding-pressure incremental contract-integrity hardening decision V0" in ROADMAP_PATH.read_text(
        encoding="utf-8"
    )
