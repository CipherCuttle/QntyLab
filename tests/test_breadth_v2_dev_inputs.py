from qntylab.breadth_v2_dev_inputs import (
    build_census, classify_transport, enumerate_market_input_plan, funding_parent_start, price_clip_range,
)
from dataclasses import asdict


def test_plan_collapses_cost_modes_without_execution():
    rows = enumerate_market_input_plan()
    assert len(rows) == 996
    assert sum(row.execution_unit_type == "SINGLE_ASSET" for row in rows) == 960
    assert sum(row.execution_unit_type == "SYNCHRONIZED_PANEL" for row in rows) == 36


def test_profile_specific_price_range_and_funding_edge():
    assert price_clip_range("DEV_2022", 73) == ("2021-12-28T23:00:00Z", "2022-12-31T22:00:00Z")
    assert funding_parent_start("DEV_2022") == "2021-12-31T23:00:00Z"


def test_transport_never_becomes_scientific_absence():
    assert classify_transport(status_code=429) == "ACQUISITION_UNRESOLVED"
    assert classify_transport(error=TimeoutError()) == "ACQUISITION_UNRESOLVED"
    assert classify_transport(status_code=404) == "SOURCE_OBJECT_ABSENT"


def test_census_preserves_frozen_denominators_and_blocking_reasons():
    rows = [{**asdict(key), "status": "BLOCKED", "evaluation_input_bundle_sha256": None, "blocking_reason": "BLOCKED_PRICE_COVERAGE"} for key in enumerate_market_input_plan()]
    census = build_census(rows, freeze_commit="2608676b1d353446b00409c63a32b4b6a362c38e")
    assert census["registered_input_records"] == 996
    assert census["registered_execution_units"] == 1992
    assert census["registered_scientific_cells"] == 3360
    assert census["blocked_input_records"] == 996
    assert census["blocking_reason_counts"] == {"BLOCKED_PRICE_COVERAGE": 996}
