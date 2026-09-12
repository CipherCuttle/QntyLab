import json
from tests._clean_tsmom_exp_v2r5_fixture import run_producer
def test_benchmarks_use_full_turnover_and_both_regimes(r5_case, tmp_path):
    out = tmp_path / "out"; result = run_producer(r5_case, out); assert result.returncode == 0, result.stderr
    ledgers = json.loads((out / "interval_ledgers.json").read_bytes())["benchmarks"]; assert ledgers["static_equal_notional_buy_and_hold:base"][0]["entry_turnover"] == 1.0; assert ledgers["static_equal_notional_buy_and_hold:base"][-1]["liquidation_turnover"] == 1.0; assert "rebalanced_equal_weight_always_long:stress" in ledgers
