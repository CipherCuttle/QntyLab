import json

from tests._clean_tsmom_exp_v2r4_fixture import r4_dir, run_verifier
from tests._clean_tsmom_exp_v2r3_fixture import r3_case, run_producer

def test_controls_are_evidence_bearing_and_complete(r3_case, tmp_path):
    producer = tmp_path / "producer"; assert run_producer(r3_case, producer).returncode == 0
    assert run_verifier(r3_case, producer, tmp_path / "report", r4_dir(tmp_path)).returncode == 0
    report = json.loads((tmp_path / "report/comparison_manifest.json").read_bytes())
    evidence = report["independent_control_evidence"]
    assert evidence["volatility_window_returns"] == 90
    assert evidence["main_first_start"] < evidence["main_last_end"]
    assert evidence["liquidation_count"] == 2
    assert evidence["funding_event_counts"]
