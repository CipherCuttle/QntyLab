import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
BASE = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v2"


def load(name):
    return json.loads((BASE / name).read_text())


def test_v1_terminal_and_v2_order_and_denominator():
    v1 = load_v1()
    census = load("mechanism_census.json")
    compile_ = load("capability_compile.json")
    assert v1["project_state"] == "CLOSED_BLOCKED"
    assert v1["blocked_reason"].startswith("No finalist can satisfy")
    assert census["selection_order"] == "MECHANISM_INTAKE_BEFORE_CAPABILITY_MATCHING"
    assert census["registered_candidate_count"] == len(census["candidates"]) == 6
    assert len(set(census["candidate_ids"])) == 6
    assert len(compile_["candidates"]) == 6


def load_v1():
    return json.loads((ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v1/input_feasibility_v0.json").read_text())


def test_finalists_are_compiled_and_static_contracts_are_safe():
    cap = load("capability_compile.json")
    contract = load("contract_compile.json")
    prereg = load("preregistration.json")
    statuses = {x["candidate_id"]: x["disposition"] for x in cap["candidates"]}
    contracts = {x["candidate_id"]: x for x in contract["candidates"]}
    for candidate_id in prereg["finalist_ids"]:
        assert statuses[candidate_id] == "CAPABILITY_PASS"
        assert contracts[candidate_id]["status"] == "CONTRACT_COMPILE_PASS"
        assert contracts[candidate_id]["duplicate_regressors"] is False
    assert prereg["finalist_count"] in (1, 2, 3)
    assert contract["all_formula_primitives_defined"]
    assert contract["all_denominator_behaviors_explicit"]
    assert contract["all_warmup_and_tails_calculable"]
    assert contract["no_lookahead"]


def test_finalist_formulas_materiality_and_timing_are_exact():
    c = {row["candidate_id"]: row for row in load("contract_compile.json")["candidates"]}
    c04, c06 = c["JFPV2_04"], c["JFPV2_06"]
    assert c04["feature"] == "CONCENTRATION_t = max_i(abs(r_i,t)) / sum_i(abs(r_i,t))"
    assert c04["return_definition"] == "r_i,t = ln(C_i,t / C_i,t-1)"
    assert c04["outcome"] == "DISPERSION_t_plus_24h = SAMPLE_SD_i(r_i,t_plus_24h)"
    assert c04["sample_sd_denominator"] == "n - 1"
    assert c04["timing"]["outcome"] == "completed hourly return vector closing at t+24h"
    assert c04["materiality_formula"] == "beta_candidate * sample_sd(CONCENTRATION_t) / sample_sd(DISPERSION_t_plus_24h)"
    assert c04["materiality_gate"] == "STANDARDIZED_BETA >= 0.01"
    assert c06["feature"].startswith("DOWNSIDE_SHARE_t =")
    assert c06["outcome"] == "PANEL_RV24_future_t = sqrt(sum_{i,k in next 24h}(r_i,k^2))"
    assert c06["materiality_formula"].startswith("(SSE_REDUCED - SSE_FULL) / SSE_REDUCED")
    assert c06["materiality_gate"] == "PARTIAL_R2 >= 0.001"
    assert c06["materiality_domain"] == "SSE_REDUCED > 0; otherwise BLOCKED_INVALID_PARTIAL_R2_DOMAIN"


def test_inference_hac_multiplicity_classification_and_result_schema():
    contract = load("contract_compile.json")
    inference = contract["inference_contract"]
    hac = contract["hac_policy"]
    classification = contract["classification_contract"]
    assert inference["full_model"].startswith("y_t ~ intercept")
    assert inference["reduced_model"].startswith("y_t ~ intercept")
    assert inference["estimator"] == "OLS with intercept"
    assert inference["p_value_type"] == "TWO_SIDED"
    assert inference["expected_direction"] == "POSITIVE"
    assert hac["bandwidth_formula"] == "floor(4 * (T / 100)^(2/9))"
    assert hac["lag_unit"] == "ORIGINS"
    assert hac["minimum_maxlag"] == 0
    assert contract["multiplicity"]["family_size"] == 2
    assert "Holm step-down FWER alpha 0.05" in contract["multiplicity"]["policy"]
    assert "beta_candidate > 0" in classification["support"]
    assert "holm_adjusted_p <= 0.05" in classification["support"]
    assert "significant negative beta" in classification["no_support"]
    assert "p-values are null" in classification["blocked"]
    assert contract["result_schema_frozen"] is True
    assert "raw_p_two_sided" in contract["result_schema"]
    assert "block_reason" in contract["result_schema"]


def test_no_downstream_or_scientific_authority():
    p = load("preregistration.json")
    assert all(value is False for key, value in p["outcome_blindness"].items() if key != "new_source_acquired")
    assert p["outcome_blindness"]["new_source_acquired"] is False
    downstream_keys = [key for key in p["authority"] if key.endswith("authorized") and key not in {"candidate_selection_authorized"}]
    assert all(p["authority"][key] is False for key in downstream_keys)
    assert p["authority"]["capital_authority"] == "NONE"
