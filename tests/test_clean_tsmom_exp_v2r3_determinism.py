import hashlib
import json

from tests._clean_tsmom_exp_v2r3_fixture import r3_case, run_producer, run_verifier


def _tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def test_producer_is_byte_for_byte_deterministic(r3_case, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        result = run_producer(r3_case, out); assert result.returncode == 0, result.stderr
    da, db = _tree(a), _tree(b)
    assert set(da) == set(db) and len(da) == len(db) and da == db
    assert json.loads((a / "artifact_manifest.json").read_bytes())["files"]


def test_independent_verifier_agrees_with_recomputation(r3_case, tmp_path):
    producer = tmp_path / "producer"; assert run_producer(r3_case, producer).returncode == 0
    report = tmp_path / "report"; result = run_verifier(r3_case, producer, report); assert result.returncode == 0, result.stderr
    comparison = json.loads((report / "comparison_manifest.json").read_bytes())
    assert comparison["source_recomputed"] is True
    assert comparison["maximum_independent_difference"] <= 1e-12
