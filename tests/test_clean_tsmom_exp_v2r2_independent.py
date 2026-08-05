from pathlib import Path

def test_independent_verifier_has_no_producer_import():
    p=(Path(__file__).parents[1]/"tools/verify_clean_tsmom_exp_v2r2_results.py").read_text()
    assert "from qntylab.clean_tsmom_exp_v2r2 import produce" not in p
    assert "run_clean_tsmom_exp_v2r2" not in p
