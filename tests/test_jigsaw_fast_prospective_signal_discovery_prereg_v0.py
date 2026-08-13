from qntylab.jigsaw_fast_prospective_signal_discovery_prereg_v0 import (
    canonical_digest,
    load_json,
    validate,
)


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
