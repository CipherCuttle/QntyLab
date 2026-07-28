import numpy as np
import pytest
from qntylab.backtest import evaluate, segments
from qntylab.data import validate
from qntylab.strategies import momentum
from qntylab.perp import causal, funding_to_bars, evaluate_perp, positions
from qntylab.experiment import _perp_splits

def test_signal_is_shifted_one_bar_no_lookahead():
    # The jump is visible at index 2; its long position begins at 3, after the jump.
    assert momentum(np.array([100.,100.,200.,200.]), 1, "long_flat").tolist() == [0.,0.,0.,1.]

def test_long_short_and_cost_accounting():
    close=np.array([100.,110.,99.,108.]); pos=np.array([1.,-1.,1.,1.])
    m=evaluate(close,pos,10)
    # Two sign flips each change exposure by two units, charged at 10 bps per unit.
    assert m["trade_count"] == 2 and m["fee_cost"] == pytest.approx(0.004)
    assert m["average_absolute_exposure"] == 1.0

def test_drawdown_and_chronological_splits():
    close=np.arange(100.,109.); pos=np.ones(9); result=segments(close,pos,0)
    assert set(result) == {"full","early","middle","late"}
    assert result["full"]["max_drawdown"] == 0.0

def test_evaluation_is_deterministic():
    close=np.array([100.,101.,99.,103.,102.]); pos=np.array([0.,1.,-1.,1.,0.])
    assert evaluate(close,pos,10) == evaluate(close,pos,10)

def test_data_validation_rejects_duplicates_bad_ohlc_and_negative_volume():
    good={"timestamp":"2021-01-01T00:00:00Z","open":"1","high":"2","low":"1","close":"2","volume":"0"}
    with pytest.raises(ValueError): validate([good, good])
    bad={**good,"high":"0.5"}
    with pytest.raises(ValueError): validate([bad])
    with pytest.raises(ValueError): validate([{**good,"volume":"-1"}])

def test_funding_event_alignment_and_signal_delay():
    stamps=["2021-01-01T00:00:00Z","2021-01-01T01:00:00Z","2021-01-01T02:00:00Z"]
    funding=funding_to_bars(stamps, [{"timestamp":"2021-01-01T00:00:00Z","funding_rate":"0.01"}])
    assert funding.tolist() == [0.01, np.nan, np.nan] or np.isnan(funding[1:]).all()
    assert causal(np.array([-1., 0., 0.])).tolist() == [0., -1., 0.]

def test_premium_and_order_flow_are_one_bar_lagged():
    close=np.ones(15) * 100; premium=np.r_[np.arange(12., dtype=float), 100., 0., 0.]; ofi=np.r_[np.zeros(12), .9, 0., 0.]; funding=np.full(15, np.nan)
    premium_position=positions("H009_premium_mean_reversion", close, premium, ofi, funding, {"lookback":12,"threshold":.5,"holding_hours":1})
    flow_position=positions("H010_taker_flow", close, premium, ofi, funding, {"lookback":1,"threshold":.15,"direction":1})
    assert premium_position[12] == 0 and premium_position[13] == -1
    assert flow_position[12] == 0 and flow_position[13] == 1

def test_perp_pnl_fee_transition_and_funding_signs():
    stamps=[f"2021-01-01T0{i}:00:00Z" for i in range(4)]
    close=np.array([100.,110.,99.,108.]); long=np.array([1.,1.,1.,1.]); short=-long
    long_result=evaluate_perp(close,long,stamps,[{"timestamp":"2021-01-01T01:00:00Z","funding_rate":".01"}],0)
    short_result=evaluate_perp(close,short,stamps,[{"timestamp":"2021-01-01T01:00:00Z","funding_rate":".01"}],0)
    flip=evaluate_perp(close,np.array([1.,-1.,1.,1.]),stamps,[],10)
    assert long_result["funding_cashflow"] == pytest.approx(-.01)
    assert short_result["funding_cashflow"] == pytest.approx(.01)
    assert flip["fees"] == pytest.approx(.004) and flip["trade_count"] == 2

def test_no_return_is_earned_across_a_gap_and_perp_is_deterministic():
    stamps=["2021-01-01T00:00:00Z","2021-01-01T01:00:00Z","2021-01-01T03:00:00Z"]
    result=evaluate_perp(np.array([100.,110.,220.]),np.ones(3),stamps,[],0)
    assert result["gap_return_count"] == 1 and result["price_pnl"] == pytest.approx(.1)
    assert result == evaluate_perp(np.array([100.,110.,220.]),np.ones(3),stamps,[],0)

def test_perp_splits_include_a_safe_final_third():
    stamps=[f"2021-01-01T{i:02d}:00:00Z" for i in range(9)]
    result=_perp_splits(np.arange(100.,109.),np.ones(9),stamps,[],0)
    assert set(result) == {"full","early","middle","late"}
