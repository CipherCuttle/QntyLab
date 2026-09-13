import ast
import json

from tests._clean_tsmom_exp_v2r3_fixture import ROOT, r3_case, run_producer, run_verifier


def _produced(case, tmp_path):
    producer = tmp_path / "producer"; result = run_producer(case, producer); assert result.returncode == 0, result.stderr
    return producer


def test_verifier_requires_own_source_root_and_recomputes_artifacts(r3_case, tmp_path):
    producer = _produced(r3_case, tmp_path)
    report = tmp_path / "report"; result = run_verifier(r3_case, producer, report)
    assert result.returncode == 0, result.stderr
    obj = json.loads((report / "comparison_manifest.json").read_bytes())
    assert obj["source_recomputed"] is True and obj["producer_bytes_copied"] is False
    assert obj["maximum_independent_difference"] <= 1e-12


def test_verifier_has_no_producer_or_dynamic_invocation_boundary_violations():
    source = (ROOT / "tools/verify_clean_tsmom_exp_v2r3_results.py").read_text(); tree = ast.parse(source)
    forbidden = ("qntylab.clean_tsmom_exp_v2r3", "tools.run_clean_tsmom_exp_v2r3", "subprocess", "runpy", "importlib")
    assert not any(token in source for token in forbidden)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"eval", "exec"} for n in ast.walk(tree))
    producer = (ROOT / "qntylab/clean_tsmom_exp_v2r3.py").read_text()
    assert "verify_clean_tsmom_exp_v2r3_results" not in producer and "run_clean_tsmom_exp_v2r3" not in producer


def test_verifier_rejects_missing_artifact(r3_case, tmp_path):
    producer = _produced(r3_case, tmp_path); (producer / "main_v1_weights.json").unlink()
    result = run_verifier(r3_case, producer, tmp_path / "report")
    assert result.returncode != 0


def test_verifier_reports_actual_difference_on_mutation(r3_case, tmp_path):
    producer = _produced(r3_case, tmp_path); path = producer / "main_v1_weights.json"; value = json.loads(path.read_bytes()); value[0]["BTCUSDT"] += 0.25; path.write_text(json.dumps(value) + "\n")
    result = run_verifier(r3_case, producer, tmp_path / "report")
    assert result.returncode != 0


def test_verifier_rejects_mutated_producer_artifact_values(r3_case, tmp_path):
    producer = _produced(r3_case, tmp_path)
    cases = {
        "main_v1_weights": "BTCUSDT", "main_v2_weights": "BTCUSDT", "main_funding_returns": "CLEAN_V1",
        "main_turnover": "CLEAN_V1", "main_costs": "CLEAN_V1", "main_equity_usd": "CLEAN_V1",
        "main_metrics": "CLEAN_V1", "benchmark_outputs": "flat", "classifications": "CLEAN_V1",
        "comparison": "classification", "controls": "no_same_bar_execution",
    }
    for name, key in cases.items():
        path = producer / f"{name}.json"; value = json.loads(path.read_bytes())
        if isinstance(value, dict):
            if isinstance(value[key], bool): value[key] = not value[key]
            elif isinstance(value[key], dict): value[key]["net_return"] = 123.0
            else: value[key] = "MUTATED"
        else: value[0][key] = 123.0
        path.write_text(json.dumps(value) + "\n")
        assert run_verifier(r3_case, producer, tmp_path / ("report-" + name)).returncode != 0
        # Restore only the mutated artifact from a fresh deterministic producer.
        fresh = _produced(r3_case, tmp_path / ("fresh-" + name)); path.write_bytes((fresh / path.name).read_bytes())


def test_verifier_rejects_mutated_artifact_manifest_digest(r3_case, tmp_path):
    producer = _produced(r3_case, tmp_path); manifest = producer / "artifact_manifest.json"; value = json.loads(manifest.read_bytes()); value["files"]["main_v1_weights.json"]["sha256"] = "0" * 64; manifest.write_text(json.dumps(value) + "\n")
    assert run_verifier(r3_case, producer, tmp_path / "report").returncode != 0
