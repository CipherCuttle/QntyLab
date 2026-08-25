"""Static validator for the QntySpot Ink shadow-performance preregistration.

This module is deliberately design-only.  It has no market-data reader,
network client, strategy evaluator, backtest path, or result materializer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0_PREREGISTRATION"
ARTIFACT = Path("experiments/research/qntyspot_ink_shadow_performance_v0/preregistration.json")
CANONICAL_BASE = "535f5bb03c0df1108caab0e24c1e539946acdca4"
QNTYSPOT_SOURCE = "b9a84c59bd43e7697ee970d2a7571647e5de4501"
HISTORICAL_CUTOFF = "2026-08-25T17:02:37Z"


class ContractError(ValueError):
    """Raised when the frozen preregistration contract has drifted."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def contract_digest(value: Mapping[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "preregistration_digest"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def load_preregistration(root: Path = Path(".")) -> dict[str, Any]:
    return json.loads((root / ARTIFACT).read_text(encoding="utf-8"))


def candidate_ids(value: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(row["candidate_id"] for row in value["candidate_family"]["candidates"])


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate(value: Mapping[str, Any]) -> None:
    _require(value.get("project_id") == PROJECT_ID, "project identity mismatch")
    _require(value.get("status") == "PREREGISTERED_NOT_EXECUTED", "artifact is not design-only")
    _require(value.get("preregistration_digest") == contract_digest(value), "preregistration digest mismatch")
    _require(value.get("canonical_base") == CANONICAL_BASE, "canonical base mismatch")
    _require(value.get("historical_cutoff_utc") == HISTORICAL_CUTOFF, "historical cutoff mismatch")

    binding = value["canonical_binding"]
    _require(binding["qntyspot_source_commit"] == QNTYSPOT_SOURCE, "QntySpot source mismatch")
    _require(binding["ink_chain_id"] == 57073, "chain mismatch")
    _require(binding["base_token"] == {
        "symbol": "KRAKMASK",
        "address": "0x32bcb803f696c99eb263d60a05cafd8689026575",
        "decimals": 18,
    }, "base-token binding mismatch")
    _require(binding["quote_token"] == {
        "symbol": "WETH9",
        "display_symbol": "WETH",
        "address": "0x4200000000000000000000000000000000000006",
        "decimals": 18,
    }, "quote-token binding mismatch")
    _require(binding["inkyswap_v2_factory"] == "0x458c5d5b75ccba22651d2c5b61cb1ea1e0b0f95d", "factory mismatch")
    _require(binding["inkyswap_v2_pool"] == "0xed11ed4b195e84ba9b74c4d6ce13b7a43b354264", "pool mismatch")
    _require(binding["v2_fee_semantics"] == {"fee_numerator": 997, "fee_denominator": 1000, "fee_decimal": "0.003"}, "fee mismatch")

    family = value["candidate_family"]
    _require(family["candidate_count"] == 12, "candidate count is not twelve")
    expected_spacing = ["0.02", "0.04", "0.06", "0.08"]
    expected_profit = ["0.03", "0.06", "0.09"]
    expected = (
        "QSP_LADDER_S02_P03", "QSP_LADDER_S02_P06", "QSP_LADDER_S02_P09",
        "QSP_LADDER_S04_P03", "QSP_LADDER_S04_P06", "QSP_LADDER_S04_P09",
        "QSP_LADDER_S06_P03", "QSP_LADDER_S06_P06", "QSP_LADDER_S06_P09",
        "QSP_LADDER_S08_P03", "QSP_LADDER_S08_P06", "QSP_LADDER_S08_P09",
    )
    rows = family["candidates"]
    _require(tuple(row["spacing"] for row in rows[0::3]) == tuple(expected_spacing), "spacing order drift")
    _require(tuple(row["profit_target"] for row in rows[:3]) == tuple(expected_profit), "profit order drift")
    _require(candidate_ids(value) == expected, "candidate Cartesian product drift")
    _require(len(set(candidate_ids(value))) == 12, "candidate IDs are not unique")
    _require(family["hidden_candidate_expansion"] is False, "hidden candidate expansion enabled")
    _require(family["indicators"] == [], "indicator added")
    _require(family["other_search"] is False, "search outside family enabled")

    split = value["history_boundary"]
    _require(split["t0_definition"] == "first eligible canonical pool-state observation at or after historical reconstructability", "T0 drift")
    _require(split["t1"] == HISTORICAL_CUTOFF, "T1 drift")
    _require(split["dev_end_formula"] == "T0 + floor(0.60 * (T1 - T0))", "DEV split drift")
    _require(split["dev_interval"] == "[T0, DEV_END]" and split["outer_interval"] == "(DEV_END, T1]", "interval boundary drift")
    _require(split["minimums_days"] == {"total_calendar_history": 30, "dev": 18, "outer": 12}, "minimum history drift")
    _require(split["random_split"] is False and split["boundary_may_move_after_outcomes"] is False, "temporal leakage enabled")

    execution = value["execution_semantics"]
    _require(execution["fill_rule"] == "fill_block > decision_block", "same-block fill enabled")
    _require(execution["same_block_events_cannot_chain"] is True, "same-block chaining enabled")
    _require(execution["historical_path_mutable_by_simulated_trades"] is False, "historical path mutation enabled")
    _require(execution["simulated_agent"] == "PRICE_TAKER", "agent is not a price taker")
    _require(execution["simultaneous_entries"] == "aggregate scheduled WETH inputs into one hypothetical AMM trade", "entry aggregation drift")
    _require(execution["fill_validity"] == ["available WETH and inventory", "exact integer AMM arithmetic", "impact cap", "strictly later block", "eligible reserve state"], "fill-validity drift")
    _require(execution["invalid_fill"] == "NO_FILL; never synthesize partial fills or mutate historical reserves", "invalid-fill drift")
    _require(execution["no_later_fill"] == "NO_FILL", "no-fill rule drift")
    _require(execution["no_same_observation_reentry"] is True, "same-observation reentry enabled")

    capital = value["capital_rule"]
    _require(capital["reference_initial_wealth_cap_weth"] == "1.0", "wealth cap drift")
    _require(capital["max_single_trade_mechanical_impact_bps"] == 50, "impact cap drift")
    _require(capital["minimum_viable_initial_wealth_weth"] == "0.01", "minimum wealth drift")
    _require(capital["search"] == "descending integer WETH atomic units from 1 WETH until the exact impact predicate passes", "capital search drift")
    _require(capital["outer_reuses_frozen_dev_wealth"] is True and capital["outer_resizing_forbidden"] is True, "outer capital resizing enabled")
    _require(capital["allocation_atomic_rounding"] == {"entry_1": "floor(cycle_budget / 3)", "entry_2": "floor(cycle_budget / 3)", "entry_3": "cycle_budget - entry_1 - entry_2"}, "allocation rounding drift")

    economics = value["amm_economics"]
    _require(economics["buy_output"] == "floor(r_token * amount_in * 997 / (r_weth * 1000 + amount_in * 997))", "buy formula drift")
    _require(economics["sell_output"] == "floor(r_weth * amount_in * 997 / (r_token * 1000 + amount_in * 997))", "sell formula drift")
    _require(economics["reserve_path"] == "immutable historical reserves; hypothetical trades never update subsequent reserves", "reserve mutation drift")
    _require(economics["impact_definition"] == "exact fee-adjusted constant-product average execution versus pre-trade reserve spot, excluding the 997/1000 fee", "impact definition drift")
    _require(economics["terminal_inventory_mark"] == "one exact hypothetical executable full liquidation against final eligible reserves, including fee, impact, and liquidation gas", "terminal mark drift")

    selection = value["dev_selection"]
    _require(selection["inputs"] == "DEV only", "selection input leakage")
    _require(selection["selected_candidate_is_immutable_before_outer"] is True, "candidate freeze missing")
    _require(selection["ranking"] == ["highest terminal executable WETH wealth", "if tied within <= 1 atomic WETH unit: lower maximum drawdown", "then lower turnover", "then fewer hypothetical trades", "then smaller spacing S", "then smaller profit target P", "then lexical candidate ID"], "selection ranking drift")
    _require(selection["dev_results_persisted_before_outer"] is True, "DEV persistence gate missing")
    _require(selection["dev_result_required_fields"] == ["all 12 candidate rows", "primary and stress cost model identity", "initial WETH", "terminal executable WETH wealth", "maximum drawdown", "turnover", "transaction counts", "cost attributions", "terminal inventory", "selected candidate", "selected candidate digest"], "DEV result schema drift")
    _require(selection["selected_candidate"] is None and selection["selected_candidate_digest"] is None, "outcome populated in preregistration")

    gas = value["cost_model"]["gas"]
    _require(gas["mode"] == "DEV_DERIVED_IF_AVAILABLE_ELSE_SENSITIVITY", "gas mode drift")
    _require(gas["receipt_threshold"] == 30 and gas["sample_max"] == 30, "gas receipt threshold drift")
    _require(gas["sensitivity_grid_weth"] == ["0", "0.000001", "0.00001", "0.0001", "0.001"], "gas sensitivity drift")
    _require(gas["fallback_selection_gas_weth"] == "0.00001" and gas["fallback_label"] == "ASSUMED_GAS_SELECTION_MODEL", "fallback gas drift")
    _require(value["cost_model"]["primary"] == "AMM fee + exact impact + selected gas per hypothetical transaction", "primary cost drift")
    _require(value["cost_model"]["stress"] == "AMM fee + exact impact + DEV_GAS_P90 per hypothetical transaction", "stress cost drift")

    baselines = value["baselines"]
    _require(tuple(row["id"] for row in baselines) == ("HOLD_WETH", "BUY_AND_HOLD_KRAKMASK", "PERIODIC_DCA", "DUMB_SYMMETRIC_GRID", "SELECTED_QNTYSPOT_LADDER"), "baseline set/order drift")
    _require(value["baseline_contract"]["identical_initial_wealth"] is True and value["baseline_contract"]["identical_execution_semantics"] is True, "baseline comparability drift")
    _require(value["qualification_fixture"]["is_strategy"] is False, "qualification fixture became strategy evidence")

    outer = value["outer_contract"]
    _require(outer["initial_access"] == "INACCESSIBLE", "OUTER was available before freeze")
    _require(outer["release_gate"] == ["SELECTED_CANDIDATE", "SELECTED_CANDIDATE_DIGEST"], "OUTER release gate drift")
    _require(outer["evaluation_limit"] == 1 and outer["rerun_forbidden"] is True, "OUTER rerun loophole")
    _require(outer["invalidated_state"] == "OUTER_CONSUMED_INVALID", "invalid OUTER state not preserved")
    _require(outer["parameter_tuning_on_outer"] is False and outer["future_information_across_boundary"] is False, "OUTER leakage enabled")

    authority = value["authority_and_receipts"]
    for key in ("scientific_execution_authorized", "market_data_access_authorized", "historical_economic_outcome_inspection_authorized", "backtest_authorized", "strategy_test_authorized", "research_ledger_mutation_authorized", "qntyspot_changed", "research_ledger_state_changed"):
        _require(authority[key] is False, f"authority/receipt drift: {key}")
    _require(authority["market_network_count"] == 0 and authority["market_data_acquisition_count"] == 0, "market access receipt is nonzero")
    _require(authority["historical_outcome_read_count"] == 0 and authority["backtest_count"] == 0 and authority["strategy_test_count"] == 0, "outcome execution receipt is nonzero")
    _require(authority["trading_authority"] == "NONE" and authority["capital_authority"] == "NONE", "capital/trading authority present")

    _require(value["result_classification"]["alpha_claim"] is False, "alpha claim enabled")
    _require(value["artifact_policy"]["results_present"] is False and value["artifact_policy"]["real_gas_sample_present"] is False, "outcome artifact present")


if __name__ == "__main__":
    validate(load_preregistration())
