from pathlib import Path

from qntylab import project_context
from qntylab.jigsaw_fast_prospective_signal_discovery_prereg_v0 import (
    canonical_digest,
    load_json,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_preregistration_validates():
    validate()


def test_exact_three_candidate_denominator_and_digest():
    census = load_json("candidate_census.json")
    assert [c["candidate_id"] for c in census["candidates"]] == ["JFP01", "JFP02", "JFP03"]
    assert canonical_digest(census, "candidate_census_digest") == census["candidate_census_digest"]


def test_execution_and_authority_are_closed():
    prereg = load_json("preregistration.json")
    assert prereg["status"] == "NOT_EXECUTED"
    assert prereg["authority"]["input_materialization_authorized"] is False
    assert prereg["authority"]["historical_execution_authorized"] is False
    assert prereg["authority"]["qnty_mutation_authorized"] is False
    assert prereg["authority"]["capital_authority"] == "NONE"
    assert prereg["historical_contract"]["shadow_observation_eligible"].startswith("TRUE only")
    assert prereg["historical_contract"]["terminal_classifications"] == [
        "DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE",
        "NO_DISCOVERY_SUPPORT_FOUND",
        "BLOCKED_GLOBAL",
        "BLOCKED_CANDIDATE",
    ]
    assert "JFP01, JFP02, JFP03" in prereg["historical_contract"]["result_semantics"]


def test_prohibited_classes_and_no_rescue_are_explicit():
    census = load_json("candidate_census.json")
    assert len(census["candidates"]) == 3
    assert {"open interest", "liquidation flow", "order-book depth", "ML", "volume-surprise multiplication"} <= set(census["prohibited_candidate_classes"])
    assert all("No " in c["no_rescue_rule"] for c in census["candidates"])


def test_jfp01_boundary_incremental_design_and_jfp03_afi():
    census = load_json("candidate_census.json")
    jfp01, _, jfp03 = census["candidates"]
    assert "[t,t+10s)" in jfp01["feature"]
    assert "[t-10s,t)" in jfp01["generic_flow_control"]
    assert "beta_boundary" in jfp01["primary_metric_statistic"]
    assert "2024-11-01T00:00:00Z" in jfp01["historical_discovery_window"]
    assert "AFI_t = abs(2 * BUY_SHARE_t - 1)" in jfp03["feature"]
    assert "* log" not in jfp03["feature"]
    assert "forecast" not in jfp03["materiality_rule"]


def test_input_materialization_authorization_is_exact_and_non_escalating():
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}
    active = [record for record in registry["project"] if record["state"] == "ACTIVE"]
    authorization = projects["JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_INPUT_MATERIALIZATION_V0"]
    preregistration = load_json("preregistration.json")
    census = load_json("candidate_census.json")

    # Input materialization is closed; the sole ACTIVE project is the separately governed
    # JFP historical execution authorization, not this closed materialization phase.
    assert len(active) == 1
    assert active[0]["project_id"] == "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_HISTORICAL_EXECUTION_V0"
    assert data["active_project"]["project_id"] == "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_HISTORICAL_EXECUTION_V0"
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["authority_level"] == "INPUT_MATERIALIZATION_ONLY"
    assert authorization["phase_type"] == "GOVERNANCE_ONLY"
    assert authorization["implementation_authorized"] is False
    assert authorization["input_materialization_authorized"] is False
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["input_reacquisition_authorized"] is False
    assert authorization["state_dispositions"] == "JFP01=BLOCKED_CANDIDATE,JFP02=BLOCKED_CANDIDATE,JFP03=READY"
    assert authorization["frozen_preregistration_project_id"] == "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_PREREG_V0"
    assert authorization["frozen_preregistration_digest"] == preregistration["preregistration_digest"]
    assert authorization["frozen_candidate_census_digest"] == census["candidate_census_digest"]
    assert authorization["frozen_candidate_ids"] == ["JFP01", "JFP02", "JFP03"]
    assert authorization["frozen_candidate_order"] == "JFP01,JFP02,JFP03"
    assert "no source substitution" in authorization["source_contract_binding"]
    assert all(authorization[field] is False for field in (
        "scientific_feature_computation_authorized",
        "scientific_outcome_computation_authorized",
        "historical_execution_authorized",
        "jigsaw_evidence_authorized",
        "prospective_deployment_authorized",
        "state_snapshot_authorized",
        "router_authorized",
        "qnty_authorized",
        "trading_authorized",
        "promotion_authorized",
    ))
    assert authorization["capital_authority"] == "NONE"
    assert "No scientific feature/outcome computation" in authorization["next_action"]


def test_frozen_jfp_contract_digests_remain_canonical():
    preregistration = load_json("preregistration.json")
    census = load_json("candidate_census.json")
    assert canonical_digest(preregistration, "preregistration_digest") == "9e9236b34b131c13cebfb0b8043ef59043b2928fa6fcd88dd7b10909d9e8ccfe"
    assert canonical_digest(census, "candidate_census_digest") == "d718dc1c60ceccdbd7a836a1e07b911a51511456289c09d7ff9b8c6af452df94"
