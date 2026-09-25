from qntylab.clean_tsmom_exp_v2r2 import START, END, TAIL, compare, classify

def test_frozen_boundaries_and_classification_boundaries():
    assert START < TAIL < END
    killed={"base":{"net_return":0,"naive_annualized_sharpe":1},"stress":{"net_return":1,"naive_annualized_sharpe":1}}
    assert classify(killed) == "PRELIMINARY_KILLED"

def test_pareto_comparison_boundaries():
    def m(x): return {"base":{"net_return":x,"naive_annualized_sharpe":x,"maximum_drawdown":0},"stress":{"net_return":x,"naive_annualized_sharpe":x,"maximum_drawdown":0}}
    assert compare(m(1), m(2)) == "V2_DOMINATES_V1"
