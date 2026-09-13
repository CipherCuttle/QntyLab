import json
from tests._clean_tsmom_exp_v2r5_fixture import run_producer
def test_artifact_metrics_reconcile_to_final_ledger(r5_case, tmp_path):
    out = tmp_path / "out"; result = run_producer(r5_case, out); assert result.returncode == 0, result.stderr
    rows = json.loads((out / "interval_ledgers.json").read_bytes())["strategies"]["CLEAN_V1"]; points = json.loads((out / "equity_artifacts.json").read_bytes())["strategies"]["CLEAN_V1"]; metrics = json.loads((out / "metrics.json").read_bytes())["strategies"]["CLEAN_V1"]
    assert len(points) == len(rows) + 1; assert abs(metrics["net_return"] - (points[-1]["equity_normalized"] - 1)) <= 1e-12; assert abs(points[-1]["equity_usd"] - rows[-1]["equity_usd_after"]) <= 1e-12
