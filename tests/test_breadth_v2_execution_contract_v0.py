import json
from pathlib import Path

import pytest

from qntylab.breadth_v2_execution import EXECUTION_UNITS, REGISTERED_SCIENTIFIC_CELLS, FundingEvent, PortfolioKernel, PriceSeries, evaluation_input_bundle_sha256, registered_candidate_mappings
from qntylab.breadth_v2_strategies import cross_sectional_weights, funding_carry_weights, price_breakout, volatility_targeting


def test_funding_uses_previous_position_and_next_target_can_see_event():
    prices = {"BTC": PriceSeries({"t0": 100, "t1": 100})}
    event = FundingEvent("BTC", "t1", 0.01, "fixture", "COMPLETE")
    result = PortfolioKernel(initial_equity=1000, fee_bps=0).execute(["t0", "t1"], prices, [event], lambda t, p, old, e: {"BTC": 1 if t == "t0" else -1}, ["BTC"])
    assert result.funding_pnl == -10
    funding_log = next(item for item in result.event_log if item["kind"] == "funding")
    assert funding_log["quantity"] == 10
    assert funding_log["held_notional_at_settlement"] == 1000


@pytest.mark.parametrize("held_notional, rate, expected", [(1000, 0.01, -10), (-1000, 0.01, 10), (1000, -0.01, 10), (-1000, -0.01, -10)])
def test_normalized_funding_signs(held_notional, rate, expected):
    prices = {"BTC": PriceSeries({"t0": 100, "t1": 100})}
    weight = held_notional / 1000
    event = FundingEvent("BTC", "t1", rate, "fixture", "COMPLETE")
    result = PortfolioKernel(initial_equity=1000, fee_bps=0).execute(["t0", "t1"], prices, [event], lambda t, p, old, e: {"BTC": weight if t == "t0" else 0}, ["BTC"])
    assert result.funding_pnl == expected


@pytest.mark.parametrize("mark_price", [None, 1, 1_000_000])
def test_optional_mark_price_is_missing_allowed_and_economically_irrelevant(mark_price):
    prices = {"BTC": PriceSeries({"t0": 100, "t1": 100})}
    event = FundingEvent("BTC", "t1", 0.01, "fixture", "COMPLETE", mark_price=mark_price)
    result = PortfolioKernel(initial_equity=1000, fee_bps=0).execute(["t0", "t1"], prices, [event], lambda t, p, old, e: {"BTC": 1 if t == "t0" else 0}, ["BTC"])
    assert result.funding_pnl == -10


def test_rate_type_contract_and_finite_rate_validation():
    prices = {"BTC": PriceSeries({"t0": 100, "t1": 100})}
    for rate_type in (None, "Regular"):
        event = FundingEvent("BTC", "t1", 0.01, "fixture", "COMPLETE", rate_type=rate_type)
        result = PortfolioKernel(initial_equity=1000, fee_bps=0).execute(["t0", "t1"], prices, [event], lambda t, p, old, e: {"BTC": 1 if t == "t0" else 0}, ["BTC"])
        assert result.funding_pnl == -10
    with pytest.raises(ValueError, match="unsupported funding rate_type"):
        FundingEvent("BTC", "t1", 0.01, "fixture", "COMPLETE", rate_type="Special")
    with pytest.raises(ValueError, match="funding_rate must be finite"):
        FundingEvent("BTC", "t1", float("nan"), "fixture", "COMPLETE")
    with pytest.raises(ValueError, match="optional mark_price"):
        FundingEvent("BTC", "t1", 0.01, "fixture", "COMPLETE", mark_price=float("inf"))


def test_funding_coverage_gap_remains_fail_closed():
    event = FundingEvent("BTC", "t1", 0.01, "fixture", "GAP")
    with pytest.raises(ValueError, match="funding evidence gap"):
        PortfolioKernel(fee_bps=0).execute(["t0", "t1"], {"BTC": PriceSeries({"t0": 100, "t1": 100})}, [event], lambda t, p, old, e: {"BTC": 0}, ["BTC"])


def test_panel_tails_and_frozen_order_ties():
    panel = [f"A{i:02d}" for i in range(20)]
    data = {s: [1, 2] for s in panel}
    weights = cross_sectional_weights(1, dict(zip(panel, data.values())), panel)
    assert [s for s in panel if weights[s] > 0] == panel[:4]
    assert [s for s in panel if weights[s] < 0] == panel[-4:]
    assert sum(weights.values()) == 0 and sum(abs(x) for x in weights.values()) == 2


def test_breakout_persists_until_lower_channel_exit():
    assert price_breakout([1, 2, 3], 2, 0) == 1
    assert price_breakout([2, 3, 2.5], 2, 1) == 1
    assert price_breakout([3, 2, 1], 2, 1) == 0


def test_vol_target_is_25_percent_formula_and_baseline_is_identity_only():
    closes = [100 + i * 0.1 for i in range(100)]
    value = volatility_targeting(closes, 24, baseline_window=720)
    assert 0.25 <= value <= 1.0
    with pytest.raises(ValueError):
        volatility_targeting(closes, 24, baseline_window=719)


def test_entry_rebalance_liquidation_and_contributions_reconcile():
    prices = {"BTC": PriceSeries({"t0": 100, "t1": 110})}
    result = PortfolioKernel(initial_equity=1000, fee_bps=100, slippage_bps=100).execute(["t0", "t1"], prices, [], lambda t, p, old, e: {"BTC": 1 if t == "t0" else 0}, ["BTC"])
    assert result.turnover_notional > 1000  # entry plus terminal liquidation
    assert sum(c.net_contribution for c in result.contributions.values()) == pytest.approx(result.final_pnl)


def test_funding_carry_uses_exact_last_n_events_and_missing_panel_fails_closed():
    panel = [f"A{i:02d}" for i in range(20)]
    events = {s: [float(i), float(i + 1), float(i + 2)] for i, s in enumerate(panel)}
    weights = funding_carry_weights(events, 2, panel)
    assert [s for s in panel if weights[s] > 0] == panel[:4]
    with pytest.raises(ValueError):
        funding_carry_weights({s: events[s] for s in panel[:-1]}, 2, panel)


def test_input_bundle_digest_is_causal_and_order_sensitive():
    kwargs = dict(instrument_contract_id="USD-M-PERP", symbols=["BTC", "ETH"], boundaries=["t0"], decision_clock="v0", assets={"BTC": {"price_content": "a", "price_provenance": "p", "funding_content": "f", "funding_provenance": "q", "coverage": "COMPLETE"}, "ETH": {"price_content": "b", "price_provenance": "p", "funding_content": "f", "funding_provenance": "q", "coverage": "COMPLETE"}})
    first = evaluation_input_bundle_sha256(**kwargs)
    changed = dict(kwargs, assets={**kwargs["assets"], "BTC": {**kwargs["assets"]["BTC"], "funding_content": "changed"}})
    assert first != evaluation_input_bundle_sha256(**changed)
    assert first != evaluation_input_bundle_sha256(**dict(kwargs, symbols=["ETH", "BTC"]))


def test_all_28_registered_candidates_map_to_supported_families():
    mappings = registered_candidate_mappings()
    assert len(mappings) == 28
    assert EXECUTION_UNITS == 1992
    assert REGISTERED_SCIENTIFIC_CELLS == 3360
