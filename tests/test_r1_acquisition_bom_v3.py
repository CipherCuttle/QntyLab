import copy
import json
from pathlib import Path

from qntylab.r1_acquisition_bom_v3 import build_bom_v3, build_required_acquisition
from qntylab.r1_input_bom import canonical_bytes


ROOT = Path(__file__).parents[1]


def frozen_inputs():
    data = ROOT / "experiments/data"
    return tuple(json.loads((data / name).read_text()) for name in (
        "r1_historical_instance_domain_v2.json", "r1_population_input_required_domain_v2.json",
        "r1_acquisition_semantics_closure_v2.json", "r1_population_market_availability_v2.json",
    ))


def test_all_frozen_streams_and_consumers_are_accounted_for():
    domain, required, acquisition, availability = frozen_inputs()
    bom = build_bom_v3(domain, required, acquisition, availability)
    plan = bom["required_acquisition"]
    assert plan["source_stream_count"] == 894
    assert plan["consumer_instance_count"] == 895
    assert plan["assignment_quarantine_count"] == 303
    mon = next(row for row in plan["streams"] if row["symbol"] == "MONUSDT")
    assert len(mon["consumer_instance_ids"]) == 2


def test_ambiguous_lifecycle_is_acquirable_but_remains_nonassignable():
    domain, required, acquisition, availability = frozen_inputs()
    plan = build_required_acquisition(domain, required, acquisition)
    quarantined = [row for row in plan["streams"] if row["unassigned_consumer_instance_ids"]]
    assert sum(len(row["unassigned_consumer_instance_ids"]) for row in quarantined) == 303
    assert all(row["funding_acquisition_plan"]["envelope_end_utc"] == "2026-06-30T23:59:59Z" for row in quarantined)
    for row in quarantined:
        assigned = {window["instrument_instance_id"] for window in row["assignment_contract"]["assignment_windows"]}
        assert not assigned.intersection(row["unassigned_consumer_instance_ids"])


def test_availability_mutation_cannot_change_required_plan_or_sha():
    domain, required, acquisition, availability = frozen_inputs()
    baseline = build_bom_v3(domain, required, acquisition, availability)
    changed = copy.deepcopy(availability)
    changed["records"][0]["state"] = "SOURCE_PRESENT"
    mutated = build_bom_v3(domain, required, acquisition, changed)
    assert baseline["required_acquisition"] == mutated["required_acquisition"]
    assert baseline["required_acquisition_sha256"] == mutated["required_acquisition_sha256"]
    assert baseline["availability_sha256"] != mutated["availability_sha256"]


def test_cutoff_funding_segments_and_sand_structural_gap_are_explicit():
    domain, required, acquisition, availability = frozen_inputs()
    bom = build_bom_v3(domain, required, acquisition, availability)
    for stream in bom["required_acquisition"]["streams"]:
        assert stream["source_acquisition_envelope"]["end_utc"] == "2026-06-30T23:59:59Z"
        assert stream["funding_acquisition_plan"]["segments"][-1]["end_utc"] == "2026-06-30T23:59:59Z"
        assert all(segment["query"]["symbol"] == stream["symbol"] for segment in stream["funding_acquisition_plan"]["segments"])
        assert stream["funding_acquisition_plan"]["pagination_contract"]["on_200_records"].startswith("bisect")
    assert bom["availability_annotation"]["sand_2024_11_04"]["classification"] == "GENUINE_STRUCTURAL_REQUIRED_DAY_ABSENCE"


def test_input_order_and_repeat_build_are_byte_identical():
    domain, required, acquisition, availability = frozen_inputs()
    first = build_bom_v3(domain, required, acquisition, availability)
    second = build_bom_v3({**domain, "instances": list(reversed(domain["instances"]))}, {**required, "records": list(reversed(required["records"]))}, {**acquisition, "streams": list(reversed(acquisition["streams"]))}, {**availability, "records": list(reversed(availability["records"]))})
    assert canonical_bytes(first) == canonical_bytes(second)
