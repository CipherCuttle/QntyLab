import hashlib
import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "real_execution_consumer_seam_successor_decision_v0/decision.json"
)
CLOSURE_PATH = ROOT / (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "real_execution_consumer_seam_implementation_authorization_v0/closure.json"
)
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
ROADMAP_PATH = ROOT / "docs/CURRENT_ROADMAP.md"
PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_DECISION_V0"
PREDECESSOR_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_REAL_EXECUTION_CONSUMER_SEAM_IMPLEMENTATION_AUTHORIZATION_V0"


def _decision() -> dict[str, object]:
    return json.loads(DECISION_PATH.read_text(encoding="utf-8"))


def _record(project_id: str) -> dict[str, object]:
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == project_id)


def test_registry_recognizes_one_governance_successor_grant() -> None:
    decision = _decision()
    record = _record(PROJECT_ID)

    assert record["phase_id"] == decision["phase_id"]
    assert record["project_id"] == decision["project_id"]
    assert record["phase_type"] == "GOVERNANCE_ONLY"
    assert record["governance_only"] is True
    assert record["state"] == "CLOSED_PASS"
    assert record["decision_artifact"] == "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/real_execution_consumer_seam_successor_decision_v0/decision.json"
    assert record["later_implementation_phases_authorized"] == 1
    assert record["later_implementation_phase"] == "FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0"
    assert record["scientific_evaluation_phases_authorized"] == 0
    assert record["scientific_evaluation_authorized"] is False
    assert record["scientific_execution_authorized"] is False
    assert record["data_access_authorized"] is False
    assert record["outcome_access_authorized"] is False
    assert record["provider_access_authorized"] is False
    assert record["claim_access_authorized"] is False
    assert record["evaluation_origin_access_authorized"] is False
    assert record["implementation_authorized"] is False
    assert record["active_project_after_closure"] == "NONE"
    assert record["router_authority"] == "NONE"
    assert record["qnty_authority"] == "NONE"
    assert record["trading_authority"] == "NONE"
    assert record["capital_authority"] == "NONE"
    assert "Funding-pressure incremental real-execution consumer seam successor decision V0" in ROADMAP_PATH.read_text(encoding="utf-8")


def test_predecessor_closure_and_registry_entry_remain_blocked() -> None:
    decision = _decision()
    predecessor = _record(PREDECESSOR_ID)

    assert hashlib.sha256(CLOSURE_PATH.read_bytes()).hexdigest() == decision["canonical_predecessor"]["closure_sha256"]
    assert decision["canonical_predecessor"]["preserved_findings"]["later_implementation_phases_authorized"] == 0
    assert predecessor["state"] == "CLOSED_BLOCKED"
    assert predecessor["authorization_created"] is False
    assert predecessor["implementation_authorized"] is False
    assert predecessor["scientific_execution_authorized"] is False
    assert predecessor["evaluation_origins_consumed"] == 0


def test_synthetic_fixture_exception_is_ephemeral_and_non_authorizing() -> None:
    decision = _decision()
    fixture = decision["authority_boundary"]["synthetic_ordering_fixture"]
    prohibitions = " ".join(decision["authority_boundary"]["pre_evaluation_prohibitions"]).lower()

    assert fixture == {
        "permitted": True,
        "identity": "EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ONLY",
        "purpose": "offline ordering instrumentation only",
        "ephemeral": True,
        "non_consuming": True,
        "not_a_real_claim": True,
        "persisted": False,
        "persistent_authorization_claim_created": False,
        "authorizes_execution": False,
        "accesses_real_data_outcomes_providers_or_origins": False,
    }
    assert "real claims" in prohibitions
    assert "real claim consumption" in prohibitions
    assert "persistent authorization claim" in prohibitions
    assert decision["load_bearing_invariants"]["claim_before_outcome"]["required"] is True
    assert "EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ACCEPTED" in decision["load_bearing_invariants"]["claim_before_outcome"]["ordering"]
    assert "not persisted" in decision["acceptance_gates"][4]
    assert "synthetic ordering fixture persisted" in decision["kill_criteria"][4]
