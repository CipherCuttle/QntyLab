from qntylab.breadth_v2_dev_inputs import (
    classify_transport, enumerate_market_input_plan, funding_parent_start, price_clip_range,
)


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
