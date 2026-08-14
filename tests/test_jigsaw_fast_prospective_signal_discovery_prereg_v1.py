from qntylab.jigsaw_fast_prospective_signal_discovery_prereg_v1 import validate, load

def test_v1_census_and_preregistration_validate():
    validate()

def test_exact_search_and_confirmatory_denominators():
    census = load("candidate_census.json"); prereg = load("preregistration.json")
    assert census["candidate_count"] == len(census["candidates"]) == 10
    assert prereg["exploratory_candidate_count"] == 10
    assert prereg["final_confirmatory_candidate_count"] == len(prereg["finalist_ids"]) == 5

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
