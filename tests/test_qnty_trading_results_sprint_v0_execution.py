"""Synthetic-only tests for the frozen Qnty trading-results readiness seam."""

from datetime import timedelta
import inspect
import json
from pathlib import Path

import pytest

from qntylab.breadth_v2_execution import evaluation_input_bundle_sha256
from qntylab.breadth_v2_sealed import EARLIEST_ELIGIBLE_ADJUDICATION_TIME, SEALED_T0, SealedAdjudicationNotAuthorized
from qntylab.qnty_trading_results_sprint_v0_execution import (
    EXPECTED_CANDIDATE_IDS,
    EXPECTED_FREEZE_SHA256,
    EXPECTED_TOTAL_EXECUTION_COUNT,
    FROZEN_PANEL_ORDER,
    ReadinessBlocked,
    adjudicate,
    build_forward_execution_plan,
    candidate_freeze_digest,
    load_freeze,
    reduce_candidate,
    validate_forward_inputs,
)
import qntylab.qnty_trading_results_sprint_v0_execution as readiness


def _bundle(candidate):
    boundaries = [
        (SEALED_T0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in range(2161)
    ]
    digest = "a" * 64
    assets = {
        symbol: {
            "price_parent_content": digest,
            "price_content": digest,
            "price_provenance": digest,
            "funding_parent_content": digest,
            "funding_content": digest,
            "funding_provenance": digest,
            "coverage": "COMPLETE",
        }
        for symbol in FROZEN_PANEL_ORDER
    }
    payload = {
        "contract": "BREADTH_V2_INPUT_BUNDLE_V0",
        "instrument_contract_id": "BINANCE_USDM_PERPETUAL_USDT_V1",
        "symbols": list(FROZEN_PANEL_ORDER),
        "boundaries": boundaries,
        "decision_clock": "UTC_HOURLY_CLOSE_FIRST_BOUNDARY_AT_OR_AFTER_EVENT_V0",
        "assets": assets,
    }
    return {
        "status": "READY",
        "evaluation_input_bundle_sha256": evaluation_input_bundle_sha256(
            instrument_contract_id=payload["instrument_contract_id"],
            symbols=payload["symbols"], boundaries=payload["boundaries"],
            decision_clock=payload["decision_clock"], assets=payload["assets"],
        ),
        "bundle_payload": payload,
        "admitted_price": {symbol: [{}] for symbol in FROZEN_PANEL_ORDER},
        "admitted_funding": {symbol: [{}] for symbol in FROZEN_PANEL_ORDER},
        "required_history": (
            {"required_price_closes": int(candidate["parameters"]["slow"]), "required_funding_signal_events": 0}
            if candidate["family"] == "MOVING_AVERAGE_TREND"
            else {"required_price_closes": int(candidate["parameters"]["lookback"]) + 1, "required_funding_signal_events": 0}
        ),
    }


def _cells(value: float = 0.01, stress_value: float | None = None):
    stress_value = value if stress_value is None else stress_value
    rows = []
    for symbol_index, symbol in enumerate(FROZEN_PANEL_ORDER):
        for cost_mode, excess in (("BASELINE_EXECUTION", value), ("STRESS_EXECUTION", stress_value)):
            rows.append({
                "symbol": symbol,
                "cost_mode": cost_mode,
                "candidate_net_return": excess,
                "benchmark_net_return": 0.0,
                "excess_return_vs_benchmark": excess,
                "gross_return": excess + 0.001,
                "turnover": 1.0,
                "trade_count": 1,
                "exposure_fraction": 0.5,
                "fee_cost": 0.001,
                "slippage_cost": 0.001,
                "funding_cost": 0.0,
                "price_pnl": excess,
                "symbol_index": symbol_index,
            })
    return rows


def test_canonical_freeze_digest_and_exact_plan_are_frozen():
    freeze = load_freeze()
    assert candidate_freeze_digest() == EXPECTED_FREEZE_SHA256
    plan = build_forward_execution_plan(freeze)
    assert len(plan) == EXPECTED_TOTAL_EXECUTION_COUNT
    assert tuple(sorted({row["candidate_id"] for row in plan})) == tuple(sorted(EXPECTED_CANDIDATE_IDS))
    assert {row["cost_mode"] for row in plan} == {"BASELINE_EXECUTION", "STRESS_EXECUTION"}
    assert {row["execution_unit_id"] for row in plan} == set(FROZEN_PANEL_ORDER)


def test_forward_bundle_identity_checks_grid_universe_and_warmup_without_execution():
    freeze = load_freeze()
    bundles = {candidate["candidate_id"]: _bundle(candidate) for candidate in freeze["candidates"]}
    assert validate_forward_inputs(freeze, bundles) == {candidate_id: None for candidate_id in EXPECTED_CANDIDATE_IDS}

    altered = json.loads(json.dumps(bundles))
    altered[EXPECTED_CANDIDATE_IDS[0]]["bundle_payload"]["symbols"] = list(reversed(FROZEN_PANEL_ORDER))
    with pytest.raises(ReadinessBlocked, match="universe mismatch"):
        validate_forward_inputs(freeze, altered)

    truncated = json.loads(json.dumps(bundles))
    truncated[EXPECTED_CANDIDATE_IDS[0]]["bundle_payload"]["boundaries"] = truncated[EXPECTED_CANDIDATE_IDS[0]]["bundle_payload"]["boundaries"][:-1]
    with pytest.raises(ReadinessBlocked, match="complete 2,160-hour"):
        validate_forward_inputs(freeze, truncated)

    wrong_warmup = json.loads(json.dumps(bundles))
    wrong_warmup[EXPECTED_CANDIDATE_IDS[0]]["required_history"]["required_price_closes"] += 1
    with pytest.raises(ReadinessBlocked, match="warmup identity"):
        validate_forward_inputs(freeze, wrong_warmup)


def test_missing_source_is_preserved_as_candidate_kill_not_denominator_deletion():
    freeze = load_freeze()
    bundles = {candidate["candidate_id"]: _bundle(candidate) for candidate in freeze["candidates"]}
    del bundles[EXPECTED_CANDIDATE_IDS[1]]["admitted_funding"][FROZEN_PANEL_ORDER[-1]]
    coverage = validate_forward_inputs(freeze, bundles)
    assert coverage[EXPECTED_CANDIDATE_IDS[1]] == "missing required asset price or funding source"
    result = reduce_candidate(candidate=freeze["candidates"][1], cells=[], blocked_reason=coverage[EXPECTED_CANDIDATE_IDS[1]])
    assert result["decision"] == "KILL"
    assert result["cell_count"] == 0
    assert result["reason_codes"]


def test_candidate_reducer_applies_frozen_cost_breadth_and_concentration_gates():
    candidate = load_freeze()["candidates"][0]
    rows = _cells(value=0.02, stress_value=0.012)
    promoted = reduce_candidate(candidate=candidate, cells=rows)
    assert promoted["decision"] == "PROMOTE"
    assert promoted["gates"]["cost_survival"] == "PASS"
    assert promoted["metrics"]["stress_positive_asset_breadth"] == 20

    killed = reduce_candidate(candidate=candidate, cells=_cells(value=0.02, stress_value=-0.001))
    assert killed["decision"] == "KILL"
    assert killed["gates"]["stress_aggregate"] == "FAIL"
    assert killed["gates"]["stress_forward_non_negative"] == "FAIL"


def test_nonfinite_metric_is_integrity_kill():
    candidate = load_freeze()["candidates"][0]
    rows = _cells()
    rows[0]["price_pnl"] = float("nan")
    result = reduce_candidate(candidate=candidate, cells=rows)
    assert result["decision"] == "KILL"
    assert result["gates"]["integrity"] == "FAIL"
    assert "nonfinite_metric" in result["reason_codes"]


def test_unsupported_funding_execution_is_candidate_kill(monkeypatch):
    freeze = load_freeze()
    candidate = freeze["candidates"][0]

    def unsupported_funding(**kwargs):
        raise ValueError("unsupported funding rate_type")

    monkeypatch.setattr(readiness, "execute_candidate_and_benchmark", unsupported_funding)
    result = readiness._execute_candidate(candidate, _bundle(candidate))
    assert result["decision"] == "KILL"
    assert any("funding_blocked" in reason for reason in result["reason_codes"])


def test_adjudication_gate_runs_before_any_forward_bundle_access():
    freeze = load_freeze()

    class ExplodingMapping(dict):
        def __getitem__(self, key):
            raise AssertionError("forward bundle was accessed before maturity")

    with pytest.raises(SealedAdjudicationNotAuthorized):
        adjudicate(
            as_of=EARLIEST_ELIGIBLE_ADJUDICATION_TIME - timedelta(hours=1),
            freeze=freeze,
            bundles_by_candidate=ExplodingMapping(),
        )


def test_readiness_module_has_no_network_or_ledger_append_path():
    source = inspect.getsource(__import__("qntylab.qnty_trading_results_sprint_v0_execution", fromlist=["x"]))
    assert "requests" not in source and "urllib" not in source
    assert "record_breadth_v2_evaluation" not in source
    assert "append_canonical_event" not in source
