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


def test_no_downstream_or_scientific_authority():
    p = load("preregistration.json")
    assert all(value is False for key, value in p["outcome_blindness"].items() if key != "new_source_acquired")
    assert p["outcome_blindness"]["new_source_acquired"] is False
    downstream_keys = [key for key in p["authority"] if key.endswith("authorized") and key not in {"candidate_selection_authorized"}]
    assert all(p["authority"][key] is False for key in downstream_keys)
    assert p["authority"]["capital_authority"] == "NONE"
