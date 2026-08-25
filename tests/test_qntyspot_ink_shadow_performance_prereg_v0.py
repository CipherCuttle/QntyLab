import ast
import hashlib
import json
from pathlib import Path

import qntylab.qntyspot_ink_shadow_performance_prereg_v0 as prereg


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / prereg.ARTIFACT


def load():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_digest_and_static_validator_are_self_consistent():
    value = load()
    body = {key: item for key, item in value.items() if key != "preregistration_digest"}
    assert value["preregistration_digest"] == hashlib.sha256(prereg.canonical_bytes(body)).hexdigest()
    prereg.validate(value)


def test_exactly_twelve_candidates_and_exact_cartesian_family():
    value = load()
    family = value["candidate_family"]
    assert family["candidate_count"] == 12
    assert len(family["candidates"]) == 12
    assert prereg.candidate_ids(value) == (
        "QSP_LADDER_S02_P03", "QSP_LADDER_S02_P06", "QSP_LADDER_S02_P09",
        "QSP_LADDER_S04_P03", "QSP_LADDER_S04_P06", "QSP_LADDER_S04_P09",
        "QSP_LADDER_S06_P03", "QSP_LADDER_S06_P06", "QSP_LADDER_S06_P09",
        "QSP_LADDER_S08_P03", "QSP_LADDER_S08_P06", "QSP_LADDER_S08_P09",
    )
    assert len(set(prereg.candidate_ids(value))) == 12
    assert family["hidden_candidate_expansion"] is False
    assert family["other_search"] is False
    assert family["indicators"] == []


def test_candidate_parameters_are_deterministic_and_no_outcome_is_frozen():
    value = load()
    assert [(row["candidate_id"], row["spacing"], row["profit_target"]) for row in value["candidate_family"]["candidates"]] == [
        ("QSP_LADDER_S02_P03", "0.02", "0.03"), ("QSP_LADDER_S02_P06", "0.02", "0.06"), ("QSP_LADDER_S02_P09", "0.02", "0.09"),
        ("QSP_LADDER_S04_P03", "0.04", "0.03"), ("QSP_LADDER_S04_P06", "0.04", "0.06"), ("QSP_LADDER_S04_P09", "0.04", "0.09"),
        ("QSP_LADDER_S06_P03", "0.06", "0.03"), ("QSP_LADDER_S06_P06", "0.06", "0.06"), ("QSP_LADDER_S06_P09", "0.06", "0.09"),
        ("QSP_LADDER_S08_P03", "0.08", "0.03"), ("QSP_LADDER_S08_P06", "0.08", "0.06"), ("QSP_LADDER_S08_P09", "0.08", "0.09"),
    ]
    assert value["dev_selection"]["selected_candidate"] is None
    assert value["dev_selection"]["selected_candidate_digest"] is None
    assert value["artifact_policy"]["results_present"] is False


def test_canonical_binding_and_split_formula_are_frozen():
    value = load()
    assert value["canonical_base"] == "535f5bb03c0df1108caab0e24c1e539946acdca4"
    assert value["canonical_binding"]["qntyspot_source_commit"] == "b9a84c59bd43e7697ee970d2a7571647e5de4501"
    assert value["historical_cutoff_utc"] == "2026-08-25T17:02:37Z"
    split = value["history_boundary"]
    assert split["dev_end_formula"] == "T0 + floor(0.60 * (T1 - T0))"
    assert split["dev_interval"] == "[T0, DEV_END]"
    assert split["outer_interval"] == "(DEV_END, T1]"
    assert split["minimums_days"] == {"total_calendar_history": 30, "dev": 18, "outer": 12}
    assert split["random_split"] is False
    assert split["boundary_may_move_after_outcomes"] is False


def test_outer_is_inaccessible_until_freeze_and_can_be_consumed_once():
    outer = load()["outer_contract"]
    assert outer["initial_access"] == "INACCESSIBLE"
    assert outer["release_gate"] == ["SELECTED_CANDIDATE", "SELECTED_CANDIDATE_DIGEST"]
    assert outer["evaluation_limit"] == 1
    assert outer["rerun_forbidden"] is True
    assert outer["invalidated_state"] == "OUTER_CONSUMED_INVALID"
    assert outer["parameter_tuning_on_outer"] is False


def test_conservative_execution_forbids_same_block_and_path_mutation():
    execution = load()["execution_semantics"]
    assert execution["fill_rule"] == "fill_block > decision_block"
    assert execution["same_block_events_cannot_chain"] is True
    assert execution["no_same_observation_reentry"] is True
    assert execution["no_later_fill"] == "NO_FILL"
    assert execution["historical_path_mutable_by_simulated_trades"] is False
    assert execution["simultaneous_entries"] == "aggregate scheduled WETH inputs into one hypothetical AMM trade"
    assert execution["fill_validity"] == ["available WETH and inventory", "exact integer AMM arithmetic", "impact cap", "strictly later block", "eligible reserve state"]
    assert execution["invalid_fill"].startswith("NO_FILL")


def test_capital_and_atomic_rounding_rules_are_exact():
    capital = load()["capital_rule"]
    assert capital["reference_initial_wealth_cap_weth"] == "1.0"
    assert capital["minimum_viable_initial_wealth_weth"] == "0.01"
    assert capital["max_single_trade_mechanical_impact_bps"] == 50
    assert capital["search"] == "descending integer WETH atomic units from 1 WETH until the exact impact predicate passes"
    assert capital["allocation_atomic_rounding"] == {
        "entry_1": "floor(cycle_budget / 3)",
        "entry_2": "floor(cycle_budget / 3)",
        "entry_3": "cycle_budget - entry_1 - entry_2",
    }
    assert capital["outer_resizing_forbidden"] is True


def test_amm_fee_impact_and_terminal_liquidation_are_explicit():
    value = load()
    economics = value["amm_economics"]
    assert value["canonical_binding"]["v2_fee_semantics"] == {"fee_numerator": 997, "fee_denominator": 1000, "fee_decimal": "0.003"}
    assert economics["buy_output"] == "floor(r_token * amount_in * 997 / (r_weth * 1000 + amount_in * 997))"
    assert economics["sell_output"] == "floor(r_weth * amount_in * 997 / (r_token * 1000 + amount_in * 997))"
    assert "including fee, impact, and liquidation gas" in economics["terminal_inventory_mark"]
    assert economics["reserve_path"] == "immutable historical reserves; hypothetical trades never update subsequent reserves"
    cost = value["cost_model"]
    assert cost["primary"] == "AMM fee + exact impact + selected gas per hypothetical transaction"
    assert cost["stress"] == "AMM fee + exact impact + DEV_GAS_P90 per hypothetical transaction"


def test_gas_fallback_and_primary_selection_model_are_frozen():
    gas = load()["cost_model"]["gas"]
    assert gas["mode"] == "DEV_DERIVED_IF_AVAILABLE_ELSE_SENSITIVITY"
    assert gas["receipt_threshold"] == 30
    assert gas["sample_max"] == 30
    assert gas["sensitivity_grid_weth"] == ["0", "0.000001", "0.00001", "0.0001", "0.001"]
    assert gas["fallback_selection_gas_weth"] == "0.00001"
    assert gas["fallback_label"] == "ASSUMED_GAS_SELECTION_MODEL"
    assert gas["no_empirical_gas_invention"] is True


def test_selection_function_is_deterministic_and_dev_only():
    selection = load()["dev_selection"]
    assert selection["inputs"] == "DEV only"
    assert selection["ranking"] == [
        "highest terminal executable WETH wealth",
        "if tied within <= 1 atomic WETH unit: lower maximum drawdown",
        "then lower turnover",
        "then fewer hypothetical trades",
        "then smaller spacing S",
        "then smaller profit target P",
        "then lexical candidate ID",
    ]
    assert selection["dev_results_persisted_before_outer"] is True
    assert "all 12 candidate rows" in selection["dev_result_required_fields"]
    assert "selected candidate digest" in selection["dev_result_required_fields"]
    assert selection["selected_candidate_is_immutable_before_outer"] is True


def test_accounting_contract_freezes_compounding_and_exact_replay():
    accounting = load()["accounting_contract"]
    assert accounting["state_units"] == "token and WETH balances are integer atomic units"
    assert "exact rational WETH-equivalent" in accounting["reported_wealth_units"]
    assert "next cycle budget is all available cash" in accounting["cycle_compounding"]
    assert "one declared gas amount per hypothetical transaction" in accounting["gas_timing"]
    assert "reproduce balances" in accounting["replay_integrity"]


def test_baselines_are_exact_and_comparable():
    value = load()
    assert [row["id"] for row in value["baselines"]] == [
        "HOLD_WETH", "BUY_AND_HOLD_KRAKMASK", "PERIODIC_DCA", "DUMB_SYMMETRIC_GRID", "SELECTED_QNTYSPOT_LADDER"
    ]
    assert value["baseline_contract"] == {
        "identical_initial_wealth": True,
        "identical_execution_semantics": True,
        "selection_exclusion": "DUMB_SYMMETRIC_GRID is not part of candidate selection",
    }
    assert "0%, 25%, 50%, and 75%" in value["baselines"][2]["definition"]
    assert "-5%, -10%, -15%" in value["baselines"][3]["definition"]


def test_metrics_and_classification_prevent_terminal_mark_or_goalpost_drift():
    value = load()
    required = value["metrics"]["required_per_candidate_and_baseline"]
    assert "terminal executable WETH wealth" in required
    assert "terminal KRAKMASK inventory before liquidation" in required
    assert "turnover" in required
    assert "AMM fee attribution" in required
    assert value["metrics"]["equity"].startswith("WETH cash + exact executable liquidation proceeds")
    classification = value["result_classification"]
    assert classification["alpha_claim"] is False
    assert "HOLD_WETH" in classification["VALID_PROMISING"]
    assert "DUMB_SYMMETRIC_GRID" in classification["VALID_PROMISING"]


def test_qualification_fixture_is_not_strategy_evidence():
    fixture = load()["qualification_fixture"]
    assert fixture["is_strategy"] is False
    assert fixture["is_research_authorization"] is False
    assert fixture["is_trading_authorization"] is False
    assert fixture["is_capital_authorization"] is False


def test_zero_network_execution_and_authority_receipts_are_frozen():
    authority = load()["authority_and_receipts"]
    assert authority["market_network_count"] == 0
    assert authority["market_data_acquisition_count"] == 0
    assert authority["historical_outcome_read_count"] == 0
    assert authority["backtest_count"] == 0
    assert authority["strategy_test_count"] == 0
    assert authority["outer_evaluation_count"] == 0
    assert authority["research_ledger_state_changed"] is False
    assert authority["qntyspot_changed"] is False
    assert authority["trading_authority"] == "NONE"
    assert authority["capital_authority"] == "NONE"
    assert all(authority[key] is False for key in (
        "scientific_execution_authorized", "market_data_access_authorized",
        "historical_economic_outcome_inspection_authorized", "backtest_authorized",
        "strategy_test_authorized", "research_ledger_mutation_authorized",
    ))


def test_validator_has_no_network_or_execution_dependencies():
    tree = ast.parse((ROOT / "qntylab/qntyspot_ink_shadow_performance_prereg_v0.py").read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imported <= {"__future__", "hashlib", "json", "pathlib", "typing"}


def test_artifact_policy_excludes_results_ledger_events_and_live_output():
    policy = load()["artifact_policy"]
    assert policy["results_present"] is False
    assert policy["dev_results_present"] is False
    assert policy["outer_results_present"] is False
    assert policy["real_gas_sample_present"] is False
    assert policy["research_ledger_candidate_event_present"] is False
    assert policy["live_shadow_output_present"] is False
    assert policy["qntyspot_mutation_present"] is False


def test_exactly_one_hostile_review_and_no_targeted_rereview():
    review = (ROOT / "experiments/research/qntyspot_ink_shadow_performance_v0/hostile_scientific_design_review.md").read_text(encoding="utf-8")
    assert review.count("Review count: exactly one.") == 1
    assert review.count("HOSTILE_REVIEW = PASS") == 1
    assert "Critical findings: 0" in review
    assert "High findings: 0" in review
    assert "Targeted rereview: not required and not performed." in review
