import json
from tests._clean_tsmom_exp_v2r5_fixture import run_producer
def test_tail_is_non_synthetic_projection(r5_case, tmp_path):
    out = tmp_path / "out"; result = run_producer(r5_case, out); assert result.returncode == 0, result.stderr
    ledgers = json.loads((out / "interval_ledgers.json").read_bytes())["strategies"]["CLEAN_V1"]; controls = json.loads((out / "controls.json").read_bytes()); tail = [r for r in ledgers if r["start_timestamp"] >= 1781827200000]
    assert controls["tail_transaction_cost_usd"] == sum(r["transaction_cost_usd"] for r in tail); assert controls["tail_funding_usd"] == sum(r["funding_pnl_usd"] for r in tail)
