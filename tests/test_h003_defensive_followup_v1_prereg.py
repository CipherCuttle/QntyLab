from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "experiments/specs/h003_defensive_followup_v1.json"


def _spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def test_strategy_and_costs_are_frozen() -> None:
    spec = _spec()
    assert spec["candidate_id"] == "CANDIDATE_H003_MA_48_192_LONG_FLAT"
    assert spec["variant_id"] == "variant_00eb140f03a5f6ab40600160"
    assert spec["frozen_strategy"] == {
        "fast": 48,
        "slow": 192,
        "mode": "long_flat",
        "decision_rule": "completed bar t; raw sign(MA48-MA192); negative maps to FLAT; one-bar shift so position decided at t owns t->t+1 return",
        "parameter_search_authorized": False,
        "asset_specific_parameters_authorized": False,
        "leverage": 1.0,
    }
    assert spec["cost_modes"] == [
        {"id": "zero_cost_diagnostic", "fee_bps": 0, "slippage_bps": 0},
        {"id": "baseline", "fee_bps": 10, "slippage_bps": 0},
        {"id": "stress", "fee_bps": 10, "slippage_bps": 10},
        {"id": "severe_stress", "fee_bps": 10, "slippage_bps": 20},
    ]


def test_preregistration_grants_no_execution_before_separate_activation() -> None:
    spec = _spec()
    boundary = spec["activation_boundary"]
    assert boundary["governance_state_after_this_preregistration"] == "BLOCKED"
    assert boundary["generic_trial_execution_authorized"] is False
    assert boundary["paper_shadow_recording_authorized"] is False
    assert boundary["requires_separate_git_backed_activation_after_merge"] is True
    assert spec["authority"]["execution"] == "PREREGISTRATION_ONLY_NO_TRIAL_OR_SHADOW_EXECUTION"


def test_prior_exposed_btc_eth_are_diagnostic_only_and_exactly_bound() -> None:
    diagnostic = _spec()["prior_exposed_retrospective_diagnostic"]
    assert diagnostic["prior_exposure_acknowledged"] is True
    assert diagnostic["exact_h003_btc_eth_were_previously_evaluated"] is True
    assert diagnostic["execution_authorized_by_this_preregistration"] is False
    assert diagnostic["requires_separate_git_backed_activation_after_merge"] is True
    assert "cannot create confirmatory support" in diagnostic["role"]
    assert diagnostic["prior_exposure_evidence_path"] == "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_cells.csv"
    assert [row["symbol"] for row in diagnostic["assets"]] == ["BTCUSDT", "ETHUSDT"]
    assert [row["expected_rows"] for row in diagnostic["assets"]] == [48821, 48821]
    assert [row["historical_end"] for row in diagnostic["assets"]] == [
        "2026-07-28T18:00:00Z",
        "2026-07-28T18:00:00Z",
    ]
    assert [row["raw_sha256"] for row in diagnostic["assets"]] == [
        "6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65",
        "3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187",
    ]
    identity = diagnostic["input_identity_contract"]
    assert identity["newer_full_file_may_not_replace_frozen_snapshot"] is True
    assert identity["acquisition_error_or_identity_mismatch_verdict"] == "BLOCKED_BY_INPUT_OR_INTEGRITY"
    assert "exact first expected_rows CSV rows plus header" in identity["materialization_rule"]
    assert diagnostic["interpretation"]["pass_cannot_confirm_or_promote"] is True


def test_prospective_panel_is_future_only_and_shared_across_three_assets() -> None:
    prospective = _spec()["prospective_panel"]
    assert prospective["mode"] == "paper_shadow_only"
    assert prospective["execution_authorized_by_this_preregistration"] is False
    assert prospective["requires_separate_git_backed_activation_after_merge"] is True
    assert prospective["assets"] == ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
    assert "separate activation/reopen is canonical" in prospective["activation_rule"]
    assert "one prospective origin" in prospective["activation_rule"]
    assert "ending bar timestamp is strictly greater than the prospective origin" in prospective["return_ownership_rule"]
    assert "No pre-origin return or transition cost" in prospective["return_ownership_rule"]
    assert prospective["minimum_calendar_days_before_economic_verdict"] == 180
    assert prospective["minimum_genuine_position_state_changes_per_asset_before_economic_verdict"] == 2
    assert prospective["maximum_calendar_days_for_regime_coverage_gate"] == 365
    assert prospective["interim_policy"]["economic_performance_verdict_before_maturity_forbidden"] is True
    assert prospective["interim_policy"]["parameter_changes_forbidden"] is True
    assert prospective["interim_policy"]["asset_changes_forbidden"] is True
    gate = prospective["primary_success_gate_at_maturity"]
    assert gate["all_three_assets_baseline_maximum_drawdown_must_be_shallower_than_buy_and_hold"] is True
    assert gate["minimum_wins_across_six_baseline_risk_adjusted_comparisons"] == 4
    assert len(gate["risk_adjusted_comparisons"]) == 6
    assert gate["minimum_assets_with_positive_stress_annualized_sharpe"] == 2


def test_claim_and_authority_remain_research_only() -> None:
    spec = _spec()
    assert spec["claim_boundary"]["prior_2023_holdout_failure_must_remain_preserved"] is True
    assert spec["claim_boundary"]["same_sample_sol_reruns_cannot_promote_claim"] is True
    assert spec["claim_boundary"]["prior_exposed_btc_eth_history_cannot_create_confirmatory_support"] is True
    assert spec["combined_adjudication"]["DEFENSIVE_REPLICATION_SUPPORTED"].startswith("after separate activation")
    assert spec["combined_adjudication"]["downstream_authority_after_any_verdict"].startswith("NONE")
    assert spec["authority"] == {
        "qntylab_research_only": True,
        "qnty_acceptance": "NONE",
        "qntyspot_policy": "NONE",
        "execution": "PREREGISTRATION_ONLY_NO_TRIAL_OR_SHADOW_EXECUTION",
        "capital": "NONE",
        "signing": "NONE",
        "submission": "NONE",
    }
