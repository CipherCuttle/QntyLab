import json
import hashlib
from tests._clean_tsmom_exp_v2r5_fixture import run_producer, run_verifier
def test_independent_verifier_passes(r5_case, tmp_path):
    out = tmp_path / "out"; report = tmp_path / "report"; result = run_producer(r5_case, out); assert result.returncode == 0, result.stderr; result = run_verifier(r5_case, out, report); assert result.returncode == 0, result.stderr
    receipt = json.loads((report / "comparison_manifest.json").read_bytes()); assert receipt["complete_independent_recomputation_pass"] is True; assert receipt["maximum_independent_difference"] <= 1e-12

def test_producer_a_and_b_are_byte_identical(r5_case, tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"; assert run_producer(r5_case, a).returncode == 0; assert run_producer(r5_case, b).returncode == 0
    tree = lambda root: {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert tree(a) == tree(b)
