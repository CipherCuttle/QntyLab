from __future__ import annotations

import random

import pytest

from qntylab.breadth_v2_family_decision import (
    ASSETS, COST_MODES, PERIODS, VARIANTS, _relative_value_diagnostics,
    contract_manifest, normalize_observation, receipt_digest, reduce_family,
)


def _obs(family, variant, asset, period, cost, excess, net=None):
    return {"family_id": family, "variant_id": variant, "period_id": period,
            "cost_mode": cost, "execution_unit_type": "SINGLE_ASSET",
            "execution_unit_id": asset, "input_status": "READY",
            "receipt_valid": True, "path_valid": True, "asset": asset,
            "candidate_net_return": net if net is not None else excess,
            "benchmark_net_return": 0.0, "excess_return_vs_benchmark": excess}


def _fixture(values=None, family="TIME_SERIES_MOMENTUM"):
    values = values or {(period, asset, variant): 0.02 for period in PERIODS for asset in ASSETS for variant in VARIANTS[family]}
    observations, expected = [], []
    for variant in VARIANTS[family]:
        for asset in ASSETS:
            for period in PERIODS:
                for cost in COST_MODES:
                    row = _obs(family, variant, asset, period, cost, values[(period, asset, variant)], values[(period, asset, variant)] + 0.01)
                    observations.append(row)
                    expected.append({k: row[k] for k in ("family_id", "variant_id", "execution_unit_type", "execution_unit_id", "period_id", "cost_mode") } | {"input_status": "READY"})
    return family, observations, expected


def test_contract_identity_is_timestamp_free_and_adjacency_is_frozen():
    manifest = contract_manifest()
    assert len(manifest["variants"]) == 7 and sum(map(len, manifest["variants"].values())) == 28
    assert all(len(p) == 2 for pairs in manifest["adjacency_map"].values() for p in pairs)
    assert "timestamp" not in repr(manifest).lower()


def test_winner_picking_cannot_create_neighbour_support():
    family = "TIME_SERIES_MOMENTUM"
    values = {(period, asset, variant): (10.0 if variant == VARIANTS[family][0] else -0.1) for period in PERIODS for asset in ASSETS for variant in VARIANTS[family]}
    _, observations, expected = _fixture(values)
    receipt = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert receipt["gate_results"]["neighbourhood"] == "FAIL"
    assert receipt["final_status"] == "FAIL"


def test_adjacent_support_passes_but_nonadjacent_support_does_not():
    family = "TIME_SERIES_MOMENTUM"
    family, observations, expected = _fixture({(p, a, v): (-0.1 if v in VARIANTS[family][2:] else 0.02) for p in PERIODS for a in ASSETS for v in VARIANTS[family]})
    assert reduce_family(family_id=family, observations=observations, expected_inputs=expected)["gate_results"]["neighbourhood"] == "PASS"
    family, observations, expected = _fixture({(p, a, v): (0.02 if v in (VARIANTS[family][0], VARIANTS[family][2]) else -0.1) for p in PERIODS for a in ASSETS for v in VARIANTS[family]})
    assert reduce_family(family_id=family, observations=observations, expected_inputs=expected)["gate_results"]["neighbourhood"] == "FAIL"


@pytest.mark.parametrize(("positive", "missing", "status"), [(10, 0, "PASS"), (9, 0, "FAIL"), (9, 1, "INCONCLUSIVE")])
def test_asset_breadth_keeps_twenty_asset_denominator(positive, missing, status):
    family, observations, expected = _fixture()
    for i, asset in enumerate(ASSETS):
        if i >= positive and i < positive + (20 - positive - missing):
            for row in observations:
                if row["asset"] == asset: row["excess_return_vs_benchmark"] = -0.01; row["candidate_net_return"] = -0.01
        if i >= 20 - missing:
            observations = [row for row in observations if row["asset"] != asset]
            expected = [row for row in expected if row["execution_unit_id"] != asset]
    receipt = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert receipt["registered_asset_denominator"] == 20
    assert receipt["gate_results"]["asset_breadth"] == status


def test_blocked_is_not_zero_and_is_integrity_neutral_when_not_executable():
    family, observations, expected = _fixture()
    blocked_asset = ASSETS[-1]
    observations = [row for row in observations if row["asset"] != blocked_asset]
    expected = [row for row in expected if row["execution_unit_id"] != blocked_asset]
    expected.extend({"family_id": family, "variant_id": v, "execution_unit_type": "SINGLE_ASSET", "execution_unit_id": blocked_asset, "period_id": p, "cost_mode": c, "input_status": "BLOCKED"} for v in VARIANTS[family] for p in PERIODS for c in COST_MODES)
    receipt = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert receipt["pooled_asset_scores"][blocked_asset]["status"] == "INCONCLUSIVE_ASSET"
    assert receipt["registered_asset_denominator"] == 20


def test_cost_survival_requires_matched_cell_population_and_positive_baseline():
    family, observations, expected = _fixture()
    observations = [row for row in observations if not (row["cost_mode"] == "STRESS_EXECUTION" and row["asset"] == ASSETS[0])]
    receipt = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert receipt["final_status"] == "BLOCKED"
    assert "MISSING_READY_EXECUTION" in receipt["reason_codes"]

    family, observations, expected = _fixture()
    for row in observations:
        row["excess_return_vs_benchmark"] = 0.0 if row["cost_mode"] == "BASELINE_EXECUTION" else 0.02
        row["candidate_net_return"] = row["excess_return_vs_benchmark"]
    assert reduce_family(family_id=family, observations=observations, expected_inputs=expected)["gate_results"]["cost_survival"] == "FAIL"


def test_temporal_and_concentration_gates_use_frozen_denominators():
    family = "TIME_SERIES_MOMENTUM"
    values = {(p, a, v): (0.02 if p != "DEV_2025" else -0.01) for p in PERIODS for a in ASSETS for v in VARIANTS[family]}
    _, observations, expected = _fixture(values)
    receipt = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert receipt["gate_results"]["temporal"] == "PASS"
    values = {(p, a, v): (0.02 if p == "DEV_2022" else -0.01) for p in PERIODS for a in ASSETS for v in VARIANTS[family]}
    _, observations, expected = _fixture(values)
    assert reduce_family(family_id=family, observations=observations, expected_inputs=expected)["gate_results"]["temporal"] == "FAIL"

    values = {(p, a, v): (0.40 if a == ASSETS[0] else 0.60 / 19) for p in PERIODS for a in ASSETS for v in VARIANTS[family]}
    _, observations, expected = _fixture(values)
    assert reduce_family(family_id=family, observations=observations, expected_inputs=expected)["gate_results"]["concentration"] == "FAIL"
    values = {(p, a, v): (0.35 if a == ASSETS[0] else 0.65 / 19) for p in PERIODS for a in ASSETS for v in VARIANTS[family]}
    _, observations, expected = _fixture(values)
    assert reduce_family(family_id=family, observations=observations, expected_inputs=expected)["gate_results"]["concentration"] == "PASS"


def test_volatility_targeting_has_no_risk_improvement_exception():
    family = "VOLATILITY_TARGETING"
    values = {(p, a, v): -0.01 for p in PERIODS for a in ASSETS for v in VARIANTS[family]}
    _, observations, expected = _fixture(values, family=family)
    receipt = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert receipt["gate_results"]["temporal"] == "FAIL"
    assert receipt["final_status"] == "FAIL"


def test_panel_normalization_reconciles_contributions_by_initial_equity():
    obs = {"family_id": "CROSS_SECTIONAL_MOMENTUM", "variant_id": VARIANTS["CROSS_SECTIONAL_MOMENTUM"][0], "period_id": PERIODS[0], "cost_mode": COST_MODES[0], "execution_unit_type": "SYNCHRONIZED_PANEL", "execution_unit_id": "BREADTH_V2_FIXED_PANEL_20", "input_status": "READY", "receipt_valid": True, "path_valid": True, "receipt": {"candidate_result": {"initial_equity": 1000.0, "final_pnl": 30.0}, "benchmark_result": {"final_pnl": 10.0}, "scientific_cells": [{"symbol": "BCHUSDT", "candidate_net_contribution": 20.0, "benchmark_net_contribution": 5.0, "excess_contribution_vs_benchmark": 15.0}, {"symbol": "XRPUSDT", "candidate_net_contribution": 10.0, "benchmark_net_contribution": 5.0, "excess_contribution_vs_benchmark": 5.0}]}}
    rows = normalize_observation(obs)
    assert [row["excess_score"] for row in rows] == [0.015, 0.005]
    obs["receipt"]["scientific_cells"][0]["candidate_net_contribution"] = 21.0
    with pytest.raises(ValueError, match="reconcile"):
        normalize_observation(obs)


def test_relative_value_uses_prior_boundary_target_and_enforces_exposure():
    family = "CROSS_SECTIONAL_MOMENTUM"
    longs = ASSETS[:8]; shorts = ASSETS[8:16]
    weights = {a: 0.125 for a in longs} | {a: -0.125 for a in shorts}
    assets = {a: {"price_pnl": 1.0, "funding_pnl": 0.0} for a in longs + shorts}
    obs = {"family_id": family, "cost_mode": "STRESS_EXECUTION", "path_valid": True, "candidate_path": [{"target_weights": weights, "assets": {}}, {"target_weights": weights, "assets": assets}]}
    counts, exposure, errors = _relative_value_diagnostics([obs], family)
    assert counts == {"long_positive_assets": 8, "short_positive_assets": 8}
    assert exposure["observed_boundaries"] == 1 and not errors
    bad = dict(obs, candidate_path=[obs["candidate_path"][0], {"target_weights": {a: 0.125 for a in ASSETS[:16]}, "assets": assets}])
    assert "BLOCKED_INTEGRITY_EXPOSURE_INVARIANT" in _relative_value_diagnostics([bad], family)[2]


def test_deterministic_receipt_under_random_input_order_and_no_execution_imports():
    family, observations, expected = _fixture()
    a = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    random.Random(7).shuffle(observations); random.Random(9).shuffle(expected)
    b = reduce_family(family_id=family, observations=observations, expected_inputs=expected)
    assert a == b and receipt_digest(a) == receipt_digest(b)
    source = open("qntylab/breadth_v2_family_decision.py", encoding="utf-8").read()
    assert "PortfolioKernel.execute" not in source
    assert "prepare_breadth_v2_evaluation" not in source
    assert "record_breadth_v2_evaluation" not in source
