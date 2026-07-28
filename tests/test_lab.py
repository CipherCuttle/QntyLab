import numpy as np
import pytest
from qntylab.backtest import evaluate, segments
from qntylab.data import validate
from qntylab.strategies import momentum

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
