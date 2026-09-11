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


def test_replication_assets_and_primary_gate_are_frozen() -> None:
    spec = _spec()
    replication = spec["cross_asset_replication"]
    assert replication["execution_authorized_only_after_this_prereg_is_merged"] is True
    assert [row["symbol"] for row in replication["assets"]] == ["BTCUSDT", "ETHUSDT"]
    assert [row["raw_sha256"] for row in replication["assets"]] == [
        "6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65",
        "3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187",
    ]
    gate = replication["primary_success_gate"]
    assert gate["both_assets_baseline_maximum_drawdown_must_be_shallower_than_buy_and_hold"] is True
    assert gate["minimum_wins_across_four_baseline_risk_adjusted_comparisons"] == 3
    assert len(gate["risk_adjusted_comparisons"]) == 4
    assert gate["both_assets_stress_annualized_sharpe_must_be_positive"] is True


def test_prospective_gate_cannot_peek_or_start_before_merge() -> None:
    prospective = _spec()["prospective_sol"]
    assert prospective["mode"] == "paper_shadow_only"
    assert "After this preregistration is merged to master" in prospective["activation_rule"]
    assert prospective["minimum_calendar_days_before_economic_verdict"] == 180
    assert prospective["minimum_genuine_position_state_changes_before_economic_verdict"] == 2
    assert prospective["maximum_calendar_days_for_regime_coverage_gate"] == 365
    assert prospective["interim_policy"]["economic_performance_verdict_before_maturity_forbidden"] is True
    assert prospective["interim_policy"]["parameter_changes_forbidden"] is True


def test_claim_and_authority_remain_research_only() -> None:
    spec = _spec()
    assert spec["claim_boundary"]["prior_2023_holdout_failure_must_remain_preserved"] is True
    assert spec["claim_boundary"]["same_sample_sol_reruns_cannot_promote_claim"] is True
    assert spec["combined_adjudication"]["downstream_authority_after_any_verdict"].startswith("NONE")
    assert spec["authority"] == {
        "qntylab_research_only": True,
        "qnty_acceptance": "NONE",
        "qntyspot_policy": "NONE",
        "execution": "RESEARCH_BACKTEST_AND_PAPER_SHADOW_ONLY",
        "capital": "NONE",
        "signing": "NONE",
        "submission": "NONE",
    }
