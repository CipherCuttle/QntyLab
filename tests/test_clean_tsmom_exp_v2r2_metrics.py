from qntylab.clean_tsmom_exp_v2r2 import _metric

def test_zero_volatility_sharpe_is_zero():
    m = _metric([1.0, 1.0], [0.0], 0, 0, 0, 0, 0)
    assert m["naive_annualized_sharpe"] == 0.0
    assert m["observation_count"] == 1
