from qntylab.jigsaw_fast_prospective_signal_discovery_prereg_v1 import validate, load

def test_v1_census_and_preregistration_validate():
    validate()

def test_exact_search_and_confirmatory_denominators():
    census = load("candidate_census.json"); prereg = load("preregistration.json")
    assert census["candidate_count"] == len(census["candidates"]) == 10
    assert prereg["exploratory_candidate_count"] == 10
    assert prereg["final_confirmatory_candidate_count"] == len(prereg["finalist_ids"]) == 5
    assert prereg["finalist_ids"] == ["JFPV1_02", "JFPV1_03", "JFPV1_04", "JFPV1_05", "JFPV1_10"]

def test_repaired_finalists_have_identifiable_primary_regressors():
    prereg = load("preregistration.json")
    assert all(contract["feature"] not in contract["baseline"] for contract in prereg["finalist_contracts"])
    assert "JFPV1_01" not in prereg["finalist_ids"]

def test_repair_history_is_discoverable_and_outcome_blind():
    census = load("candidate_census.json"); prereg = load("preregistration.json")
    assert census["repair_provenance"]["original_preregistration_digest"] == "035eecae9e2ecdd76d90506ce39b2fee973794866b424224235a2dce8e3dc298"
    assert prereg["repair_provenance"]["replacement_selection_used_only_frozen_census"] is True
    assert load("pre_merge_repair_v0.json")["scientific_outcomes_seen_before_repair"] is False

def test_no_execution_or_authority_leakage():
    prereg = load("preregistration.json")
    assert all(value is False for value in prereg["authority"].values() if isinstance(value, bool))
    assert prereg["authority"]["capital_authority"] == "NONE"
    assert all(value is False for value in prereg["outcome_blindness"].values())

def test_all_finalists_reuse_data_spine_and_are_complete():
    prereg = load("preregistration.json")
    assert len(prereg["finalist_contracts"]) == 5
    assert all(c["input_class"] == "DATA_SPINE_REUSE" for c in prereg["finalist_contracts"])
    assert all(c["shadowable_if_later_supported"] for c in prereg["finalist_contracts"])
