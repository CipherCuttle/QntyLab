from __future__ import annotations

import json
from pathlib import Path

from qntylab.backtest import ANNUAL_BARS


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "experiments/specs/h003_edge_falsification_v0.json"
ANALYSIS = ROOT / "experiments/specs/h003_edge_falsification_v0_analysis_contract.json"
DECISIONS = ROOT / "experiments/research/decisions.jsonl"

CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
GRAVEYARD_EVENT_ID = "event_3206c7b09c089b274ca027a5"
CANONICAL_SOL_SHA = "64bdb27a31003b0de25f3802affa8b412143a50bc8a5b76a399924626b01174a"
SEEDS = [17011, 17029, 17041, 17053, 17077, 17093, 17107, 17123, 17137, 17159]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_preregistration_is_exact_single_variant_and_preserves_prior_failure() -> None:
    spec = _json(SPEC)
    prior = spec["prior_evidence"]

    assert spec["preregistration_id"] == "H003_EDGE_FALSIFICATION_V0"
    assert spec["registration_only"] is True
    assert spec["status"] == "REGISTERED_NOT_EXECUTED"
    assert spec["scope"]["strategy_variant_count"] == 1
    assert spec["scope"]["parameter_search_allowed"] is False
    assert spec["scope"]["neighbor_parameter_testing_allowed"] is False
    assert spec["scope"]["replacement_winner_selection_allowed"] is False

    assert prior["candidate_id"] == CANDIDATE_ID
    assert prior["variant_id"] == VARIANT_ID
    assert prior["graveyard_decision_event_id"] == GRAVEYARD_EVENT_ID
    assert prior["parameters"] == {"fast": 48, "slow": 192, "mode": "long_flat"}
    assert prior["graveyard_reason_code"] == "FAILED_2023_HOLDOUT_MULTIPLE_GATES"

    decisions = [json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    graveyard = next(event for event in decisions if event.get("event_id") == GRAVEYARD_EVENT_ID)
    assert graveyard["candidate_id"] == CANDIDATE_ID
    assert graveyard["variant_id"] == VARIANT_ID
    assert graveyard["status"] == "GRAVEYARDED"
    assert "FAILED_2023_HOLDOUT_MULTIPLE_GATES" in graveyard["reason_codes"]


def test_preregistration_pins_input_costs_blocks_controls_and_verdicts() -> None:
    spec = _json(SPEC)

    assert spec["data_contract"]["canonical_csv_sha256"] == CANONICAL_SOL_SHA
    assert spec["data_contract"]["canonical_row_count"] == 49831
    assert spec["data_contract"]["canonical_start"] == "2021-01-01T00:00:00Z"
    assert spec["data_contract"]["canonical_end"] == "2026-09-08T20:00:00Z"
    assert spec["data_contract"]["post_freeze_live_continuation"]["minimum_forward_hours_before_any_forward_evidence_claim"] == 2160

    assert [block["id"] for block in spec["historical_blocks"]] == [
        "BLOCK_2021",
        "BLOCK_2022",
        "BLOCK_2023_KNOWN_HOLDOUT",
        "BLOCK_2024",
        "BLOCK_2025",
        "BLOCK_2026_TO_FREEZE",
    ]
    assert spec["cost_modes"] == {
        "zero_cost_diagnostic": {"fee_bps": 0, "slippage_bps": 0, "decision_role": "DIAGNOSTIC_ONLY"},
        "baseline": {"fee_bps": 10, "slippage_bps": 0, "decision_role": "PRIMARY"},
        "stress": {"fee_bps": 10, "slippage_bps": 10, "decision_role": "PRIMARY"},
        "severe_stress": {"fee_bps": 10, "slippage_bps": 20, "decision_role": "ROBUSTNESS"},
    }
    assert spec["control_contract"]["random_seed_set_before_results"] == SEEDS
    assert spec["benchmarks_and_controls"] == [
        "SOL_BUY_AND_HOLD",
        "CASH",
        "EXPOSURE_MATCHED_RANDOM_TIMING",
        "BLOCK_SHUFFLED_H003_SIGNAL",
        "H003_SIGNAL_DELAYED_24H",
    ]
    assert set(spec["verdict_vocabulary"]) == {
        "DEFENSIVE_EDGE_CANDIDATE",
        "FRAGILE_OR_UNPROVEN",
        "FALSIFIED",
        "BLOCKED_BY_INPUT_OR_INTEGRITY",
    }


def test_analysis_contract_removes_metric_rng_and_gap_degrees_of_freedom() -> None:
    analysis = _json(ANALYSIS)

    assert analysis["parent_preregistration_id"] == "H003_EDGE_FALSIFICATION_V0"
    assert analysis["created_before_v0_execution"] is True
    assert analysis["return_accounting"]["annual_bars"] == ANNUAL_BARS == 8760
    assert analysis["return_accounting"]["risk_free_rate"] == 0
    assert "population_stddev" in analysis["return_accounting"]["annualized_sharpe"]
    assert analysis["return_accounting"]["calmar_ratio"].startswith("annualized_return / abs(maximum_drawdown)")

    controls = analysis["control_generation"]
    assert controls["rng"] == "numpy.random.Generator(numpy.random.PCG64(seed))"
    assert controls["seeds"] == SEEDS
    assert controls["EXPOSURE_MATCHED_RANDOM_TIMING"]["comparison_statistic"] == "median metric across the 10 frozen seeds"
    assert controls["BLOCK_SHUFFLED_H003_SIGNAL"]["comparison_statistic"] == "median metric across the 10 frozen seeds"

    gap = analysis["gap_and_input_semantics"]
    assert gap["global_rule"] == "Never create an ordinary missing candle and never compute a return across a timestamp gap."
    assert len(gap["known_manifest_gaps"]) == 7
    assert gap["BLOCK_2021"]["policy"] == "SEGMENT_FAIL_CLOSED_NO_SYNTHETIC_BARS"
    assert gap["BLOCK_2023_KNOWN_HOLDOUT"]["policy"] == "USE_EXISTING_AUTHORIZED_HALT_NORMALIZATION"
    assert gap["BLOCK_2023_KNOWN_HOLDOUT"]["input_sha256"] == "62cee85e0a0f7b903fadc77a8f275e774f0ff3ecfff9fba9ea51a535376f70f1"


def test_preregistration_and_analysis_contract_grant_no_downstream_authority() -> None:
    spec = _json(SPEC)["authority"]
    analysis = _json(ANALYSIS)["authority"]

    assert spec == {
        "qntylab_only": True,
        "qnty_acceptance": "NONE",
        "qntyspot_policy": "NONE",
        "capital": "NONE",
        "signing": "NONE",
        "submission": "NONE",
        "live_trading": "FORBIDDEN",
        "paper_trading": "FORBIDDEN",
        "execution": "FORBIDDEN",
    }
    assert analysis == {
        "research_only": True,
        "qnty_acceptance": "NONE",
        "qntyspot_policy": "NONE",
        "execution": "FORBIDDEN",
        "capital": "NONE",
        "signing": "NONE",
        "submission": "NONE",
    }
