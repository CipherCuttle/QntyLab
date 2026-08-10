from datetime import datetime, timedelta, timezone
import json

import pytest

from qntylab.breadth_v2_sealed import (
    EARLIEST_ELIGIBLE_ADJUDICATION_TIME, ELIGIBLE_FAMILIES,
    ELIGIBLE_VARIANT_IDS, EXCLUDED_DEVELOPMENT_FAIL_FAMILIES,
    MINIMUM_COMPLETE_HOURS, SEALED_T0, adjudication_is_authorized,
    build_contract, derive_sealed_t0, serialize_contract,
)

UTC = timezone.utc


def test_survivors_and_full_registered_variants_are_frozen():
    assert ELIGIBLE_FAMILIES == ("MOVING_AVERAGE_TREND", "PRICE_BREAKOUT")
    assert set(EXCLUDED_DEVELOPMENT_FAIL_FAMILIES) == {
        "TIME_SERIES_MOMENTUM", "CROSS_SECTIONAL_MOMENTUM", "CROSS_SECTIONAL_REVERSAL",
        "FUNDING_CARRY", "VOLATILITY_TARGETING",
    }
    assert all(len(ids) == 4 for ids in ELIGIBLE_VARIANT_IDS.values())
    assert not set(EXCLUDED_DEVELOPMENT_FAIL_FAMILIES) & set(ELIGIBLE_VARIANT_IDS)


def test_t0_is_deterministic_and_not_caller_overridable():
    assert derive_sealed_t0() == SEALED_T0 == datetime(2026, 8, 10, 19, tzinfo=UTC)
    with pytest.raises(TypeError):
        derive_sealed_t0(datetime(2026, 1, 1, tzinfo=UTC))


def test_exact_complete_hour_boundary():
    assert MINIMUM_COMPLETE_HOURS == 2160
    assert not adjudication_is_authorized(EARLIEST_ELIGIBLE_ADJUDICATION_TIME - timedelta(hours=1))
    assert adjudication_is_authorized(EARLIEST_ELIGIBLE_ADJUDICATION_TIME)
    assert adjudication_is_authorized(EARLIEST_ELIGIBLE_ADJUDICATION_TIME + timedelta(hours=1))


def test_contract_is_outcome_free_and_deterministic():
    a = build_contract()
    b = build_contract()
    assert a == b
    assert a["observation_status"] == "SEALED_OBSERVATION_ACTIVE"
    assert a["sealed_adjudication_authorized"] is False
    assert "return" not in json.dumps(a).lower()
    assert "2023" in a["historical_holdout_policy"] and "2026" in a["historical_holdout_policy"]
    assert serialize_contract(a) == serialize_contract(b)


def test_status_only_uses_clock_and_never_changes_contract_identity():
    mature = build_contract(as_of=EARLIEST_ELIGIBLE_ADJUDICATION_TIME)
    active = build_contract(as_of=EARLIEST_ELIGIBLE_ADJUDICATION_TIME - timedelta(hours=1))
    assert mature["sealed_adjudication_authorized"] is True
    assert active["sealed_adjudication_authorized"] is False
    assert mature["contract_digest"] == active["contract_digest"]
    for key in ("SEALED_T0", "eligible_families", "eligible_variant_ids", "minimum_complete_hours", "cost_modes", "source_contracts"):
        assert mature[key] == active[key]


def test_canonical_artifact_matches_builder():
    artifact = json.load(open("experiments/results/breadth_v2_sealed_forward_observation_v0.json"))
    assert artifact == build_contract()
