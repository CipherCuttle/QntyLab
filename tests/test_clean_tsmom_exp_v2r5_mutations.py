import hashlib, json
from tests._clean_tsmom_exp_v2r5_fixture import run_producer, run_verifier
def test_manifest_preserving_value_mutation_is_semantic_mismatch(r5_case, tmp_path):
    out = tmp_path / "out"; result = run_producer(r5_case, out); assert result.returncode == 0, result.stderr
    p = out / "metrics.json"; value = json.loads(p.read_bytes()); value["strategies"]["CLEAN_V1"]["net_return"] += 0.25; p.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()); manifest = json.loads((out / "artifact_manifest.json").read_bytes()); manifest["files"][p.name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}; (out / "artifact_manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode())
    result = run_verifier(r5_case, out, tmp_path / "report"); assert result.returncode != 0 and "SEMANTIC_INDEPENDENT_MISMATCH" in result.stderr
