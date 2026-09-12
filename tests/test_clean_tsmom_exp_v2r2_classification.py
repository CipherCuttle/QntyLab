from qntylab.clean_tsmom_exp_v2r2 import classify

def test_survival_and_inconclusive_boundaries():
    def m(b, s): return {"base":{"net_return":b,"naive_annualized_sharpe":b},"stress":{"net_return":s,"naive_annualized_sharpe":s}}
    assert classify(m(1,1)) == "PRELIMINARY_SURVIVES"
    assert classify(m(1,-1)) == "PRELIMINARY_INCONCLUSIVE"
