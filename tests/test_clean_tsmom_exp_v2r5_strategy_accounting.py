import json
from tests._clean_tsmom_exp_v2r5_fixture import run_producer
def test_strategy_has_full_entry_and_final_liquidation(r5_case, tmp_path):
    out = tmp_path / "out"; result = run_producer(r5_case, out); assert result.returncode == 0, result.stderr
    rows = json.loads((out / "interval_ledgers.json").read_bytes())["strategies"]["CLEAN_V1"]; points = json.loads((out / "equity_artifacts.json").read_bytes())["strategies"]["CLEAN_V1"]
    assert rows[0]["entry_turnover"] == 1.0; assert rows[-1]["liquidation_turnover"] == 1.0; assert len(rows) == len(points) - 1; assert all(abs(r["net_return"] - (r["price_return"] + r["funding_return"] - r["transaction_cost_return"])) <= 1e-12 for r in rows)
