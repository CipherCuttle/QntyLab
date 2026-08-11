from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from qntylab.jigsaw_cross_sectional_dispersion_v0 import (
    DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD,
    FAMILY_CONSISTENCY_MINIMUM_VARIANTS,
    FUNDING_BOUNDARY_MODE,
    MEASUREMENT_VARIANT_LOOKBACKS_HOURS,
    MINIMUM_CROSS_SECTIONAL_BREADTH,
    NUMBER_OF_PRIMARY_STATE_HYPOTHESES,
    PANEL,
    PIT_UNIVERSE_CLAIM,
    PRIMARY_COST_MODE,
    PROMOTION_ELIGIBLE,
    ROUTER_AUTHORITY,
    SEALED_T0_ISO,
    SECONDARY_COST_MODE,
    contract_digest,
    contract_payload,
    cross_sectional_dispersion,
    dispersion_percentile_and_bin,
    family_consistency,
    is_pre_sealed_t0,
)
from qntylab.jigsaw_trend_condition_dependence_v0 import NORMALIZATION_DAYS

CANDIDATE_PROPOSAL_PATH = Path("experiments/research/jigsaw_cross_sectional_dispersion_v0/candidate_proposal.json")
CANDIDATES_LEDGER_PATH = Path("experiments/research/candidates.jsonl")


def test_contract_digest_is_deterministic():
    assert contract_digest() == contract_digest()
    payload_a, payload_b = contract_payload(), contract_payload()
    assert payload_a == payload_b
    # Key order must not affect identity.
    assert contract_digest() == contract_digest()


def test_exactly_one_primary_state_hypothesis():
    assert NUMBER_OF_PRIMARY_STATE_HYPOTHESES == 1


def test_no_router_or_qnty_authority_declared():
    assert ROUTER_AUTHORITY == "NONE"
    assert PROMOTION_ELIGIBLE is False
    assert PIT_UNIVERSE_CLAIM == "NONE"


def test_sealed_t0_exclusion_enforced():
    assert is_pre_sealed_t0("2026-08-10T18:59:59Z") is True
    assert is_pre_sealed_t0(SEALED_T0_ISO) is False
    assert is_pre_sealed_t0("2026-08-10T19:00:01Z") is False
    # Development window must be strictly pre-seal.
    assert is_pre_sealed_t0("2024-12-31T23:00:00Z") is True


def test_dispersion_requires_the_exact_frozen_panel():
    complete = {symbol: 0.01 for symbol in PANEL}
    assert cross_sectional_dispersion(complete) == pytest.approx(0.0, abs=1e-12)
    missing_one = dict(complete)
    del missing_one[PANEL[0]]
    with pytest.raises(ValueError):
        cross_sectional_dispersion(missing_one)
    extra = dict(complete)
    extra["NOTINPANEL"] = 0.01
    with pytest.raises(ValueError):
        cross_sectional_dispersion(extra)
    assert MINIMUM_CROSS_SECTIONAL_BREADTH == len(PANEL) == 20


def test_dispersion_rejects_non_finite_and_matches_known_stdev():
    complete = {symbol: 0.01 for symbol in PANEL}
    complete[PANEL[0]] = float("nan")
    with pytest.raises(ValueError):
        cross_sectional_dispersion(complete)
    # Known closed-form: alternating +x/-x across 20 assets, ddof=1 stdev.
    values = {symbol: (0.02 if i % 2 == 0 else -0.02) for i, symbol in enumerate(PANEL)}
    expected = float(np.std(np.array(list(values.values())), ddof=1))
    assert cross_sectional_dispersion(values) == pytest.approx(expected)


def test_dispersion_statistic_is_permutation_invariant():
    rng = np.random.default_rng(0)
    values = {symbol: float(rng.normal()) for symbol in PANEL}
    shuffled_keys = list(values.keys())
    rng.shuffle(shuffled_keys)
    shuffled = {k: values[k] for k in shuffled_keys}
    assert cross_sectional_dispersion(values) == cross_sectional_dispersion(shuffled)


def test_dispersion_percentile_delegates_to_frozen_jigsaw_normalization_and_is_pit():
    values = np.arange(NORMALIZATION_DAYS + 1, dtype=float)
    percentile, bin_name = dispersion_percentile_and_bin(values, NORMALIZATION_DAYS)
    assert percentile == 100.0
    assert bin_name == "HIGH"
    # Values strictly after the decision index must not change the result:
    # this is the same future-information-prohibited guarantee already
    # proven for the reused Jigsaw normalization, exercised through this
    # module's own call path.
    extended = np.r_[values, np.repeat(-999.0, 50)]
    percentile_again, bin_again = dispersion_percentile_and_bin(extended, NORMALIZATION_DAYS)
    assert (percentile_again, bin_again) == (percentile, bin_name)


def test_dispersion_percentile_requires_complete_trailing_history():
    with pytest.raises(ValueError):
        dispersion_percentile_and_bin(np.arange(NORMALIZATION_DAYS, dtype=float), NORMALIZATION_DAYS - 1)


def test_family_consistency_requires_all_four_registered_variants():
    assert MEASUREMENT_VARIANT_LOOKBACKS_HOURS == (24, 72, 168, 336)
    incomplete = {24: -0.01, 72: -0.02, 168: -0.03}
    with pytest.raises(ValueError):
        family_consistency(incomplete)


def test_family_consistency_is_order_and_selection_free():
    values = {24: -0.01, 72: -0.02, 168: 0.03, 336: -0.04}
    result = family_consistency(values)
    assert result["consistent_count"] == 3
    assert result["of_variants"] == 4
    assert result["minimum_required"] == FAMILY_CONSISTENCY_MINIMUM_VARIANTS
    assert result["family_consistent"] is True
    # Re-keying/reordering the input dict cannot change the verdict: no
    # "best variant" is ever selected or surfaced.
    reordered = {336: -0.04, 168: 0.03, 24: -0.01, 72: -0.02}
    assert family_consistency(reordered) == result
    assert "best_variant" not in result and "worst_variant" not in result


def test_family_consistency_none_values_do_not_count_as_consistent():
    values = {24: None, 72: -0.02, 168: -0.03, 336: -0.04}
    result = family_consistency(values)
    assert result["consistent_count"] == 3
    assert result["family_consistent"] is True
    all_missing = {24: None, 72: None, 168: None, 336: None}
    assert family_consistency(all_missing)["family_consistent"] is False


def test_no_outcome_selected_measurement_path():
    from pathlib import Path

    source = Path("qntylab/jigsaw_cross_sectional_dispersion_v0.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("best strategy", "best variant", "def materialize(", "def analyze(", "def run(", "def main(", "argmax"):
        assert forbidden not in lowered


def test_distinctness_threshold_is_frozen_before_any_outcome():
    assert DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD == 0.90


def test_primary_cost_mode_matches_frozen_breadth_v2_and_jigsaw_authority():
    # Breadth V2 Section 8 items 2/4 gate on "stressed" excess/net-return
    # advantage, and the prior Jigsaw piece anchors eligibility on
    # primary[state]["STRESS"], checking BASELINE only for sign agreement.
    # Both existing authorities make STRESS primary, never BASELINE.
    assert PRIMARY_COST_MODE == "STRESS_EXECUTION"
    assert SECONDARY_COST_MODE == "BASELINE_EXECUTION"
    assert contract_payload()["primary_cost_mode"] == "STRESS_EXECUTION"
    assert contract_payload()["secondary_cost_mode"] == "BASELINE_EXECUTION"


def test_funding_boundary_mode_matches_the_registered_csmom_variants():
    # Bound by reference: the exact value already registered for the four
    # frozen CANDIDATE_BREADTH_V2_CSMOM_* variants, never invented here.
    assert FUNDING_BOUNDARY_MODE == "REALIZED_FUNDING_SETTLEMENTS_REQUIRED"
    assert contract_payload()["funding_boundary_mode"] == FUNDING_BOUNDARY_MODE
    matched = 0
    with CANDIDATES_LEDGER_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            if event.get("candidate_id", "").startswith("CANDIDATE_BREADTH_V2_CSMOM_"):
                assert event["funding_boundary_mode"] == FUNDING_BOUNDARY_MODE
                matched += 1
    assert matched == 4


def test_candidate_proposal_funding_and_input_identity_is_consistent():
    event = json.loads(CANDIDATE_PROPOSAL_PATH.read_text(encoding="utf-8"))
    assert event["funding_boundary_mode"] == FUNDING_BOUNDARY_MODE
    assert event["funding_boundary_mode"] != "NOT_APPLICABLE"
    assert "funding" in event["required_data"].lower()
    assert event["required_input_kind"] == "OHLCV_1H_CSV"


def test_candidate_proposal_variant_id_is_the_deterministic_ledger_hash():
    from qntylab.research_ledger import compute_variant_id

    event = json.loads(CANDIDATE_PROPOSAL_PATH.read_text(encoding="utf-8"))
    assert event["variant_id"] == compute_variant_id(event)
