import ast
import hashlib
import json
import subprocess
import sys

from tests._clean_tsmom_exp_v2r3_fixture import ROOT, r3_case, run_producer
from tests._clean_tsmom_exp_v2r4_fixture import r4_dir, run_verifier

NAMES = ("main_panel", "main_signals", "main_v1_weights", "main_v2_weights", "main_funding_assignments", "main_funding_returns", "main_turnover", "main_costs", "main_equity_usd", "main_equity_normalized", "main_metrics", "tail_metrics", "benchmark_outputs", "controls", "classifications", "comparison", "final_liquidation")

def test_complete_independent_recomputation_and_receipts(r3_case, tmp_path):
    producer = tmp_path / "producer"; result = run_producer(r3_case, producer); assert result.returncode == 0, result.stderr
    result = run_verifier(r3_case, producer, tmp_path / "report", r4_dir(tmp_path)); assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report/comparison_manifest.json").read_bytes())
    assert report["all_artifacts_independently_recomputed"] is True
    assert report["producer_bytes_copied"] is False
    assert report["maximum_independent_difference"] <= 1e-12
    assert set(report["checked"]) == set(NAMES)

def test_producer_a_and_b_are_byte_identical(r3_case, tmp_path):
    a, b = tmp_path / "producer-a", tmp_path / "producer-b"
    assert run_producer(r3_case, a).returncode == 0
    assert run_producer(r3_case, b).returncode == 0
    tree = lambda root: {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert tree(a) == tree(b)

def test_r4_forbids_producer_r2_r3_and_dynamic_invocation():
    source = (ROOT / "tools/verify_clean_tsmom_exp_v2r4_results.py").read_text()
    assert not any(token in source for token in ("qntylab.clean_tsmom_exp_v2r3", "tools.run_clean_tsmom_exp_v2r3", "qntylab.clean_tsmom_exp_v2r2", "subprocess", "runpy", "importlib", "os.system"))
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"} for node in ast.walk(tree))
    assert "verify_clean_tsmom_exp_v2r4_results" not in (ROOT / "qntylab/clean_tsmom_exp_v2r3.py").read_text()

def test_integrity_failures_remain_distinct(r3_case, tmp_path):
    producer = tmp_path / "producer"; assert run_producer(r3_case, producer).returncode == 0
    verification = r4_dir(tmp_path)
    (producer / "main_panel.json").unlink()
    result = run_verifier(r3_case, producer, tmp_path / "report", verification)
    assert result.returncode != 0 and "INTEGRITY_FAILURE" in result.stderr
