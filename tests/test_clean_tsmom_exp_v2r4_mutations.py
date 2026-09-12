import hashlib
import json
import shutil

import pytest

from tests._clean_tsmom_exp_v2r4_fixture import r4_dir, run_verifier
from tests._clean_tsmom_exp_v2r3_fixture import r3_case, run_producer

MUTATIONS = {
    "main_panel": (0, "BTCUSDT"), "main_signals": (0, "BTCUSDT"), "main_v1_weights": (0, "BTCUSDT"), "main_v2_weights": (0, "BTCUSDT"),
    "main_funding_assignments": (0, "BTCUSDT"), "main_funding_returns": ("CLEAN_V1", "value"), "main_turnover": ("CLEAN_V1", "turnover"),
    "main_costs": ("CLEAN_V1", "base"), "main_equity_usd": ("CLEAN_V1", "value"), "main_equity_normalized": ("CLEAN_V1", "value"),
    "main_metrics": ("CLEAN_V1", "base.net_return"), "tail_metrics": ("CLEAN_V1", "net_return"), "benchmark_outputs": ("flat", "main.net_return"),
    "controls": ("no_same_bar_execution", None), "classifications": ("CLEAN_V1", None), "comparison": ("classification", None), "final_liquidation": ("CLEAN_V1", "turnover"),
}

def _mutate(value, selector):
    key, subkey = selector
    if isinstance(key, int):
        value[key][subkey] = (value[key][subkey] + 0.25) if isinstance(value[key][subkey], (int, float)) else 999
    elif subkey is None:
        value[key] = (not value[key]) if isinstance(value[key], bool) else "MUTATED"
    elif "." in subkey:
        a, b = subkey.split("."); value[key][a][b] = 123.0
    else:
        target = value[key]
        if isinstance(target, list): target[0][subkey] = 123.0
        else: target[subkey] = 123.0

@pytest.mark.parametrize("name,selector", MUTATIONS.items())
def test_manifest_preserving_value_mutations_are_semantic_mismatches(r3_case, tmp_path, name, selector):
    producer = tmp_path / "producer"; assert run_producer(r3_case, producer).returncode == 0
    path = producer / f"{name}.json"; value = json.loads(path.read_bytes()); _mutate(value, selector); path.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
    manifest_path = producer / "artifact_manifest.json"; manifest = json.loads(manifest_path.read_bytes()); manifest["files"][path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}; manifest_path.write_bytes((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode())
    result = run_verifier(r3_case, producer, tmp_path / "report", r4_dir(tmp_path))
    assert result.returncode != 0, name
    assert "SEMANTIC_INDEPENDENT_MISMATCH" in result.stderr, result.stderr
    assert f"first_mismatch_artifact={name}" in result.stderr, result.stderr

def test_noncanonical_serialization_is_integrity_failure(r3_case, tmp_path):
    producer = tmp_path / "producer"; assert run_producer(r3_case, producer).returncode == 0
    path = producer / "main_panel.json"; path.write_text(json.dumps(json.loads(path.read_bytes()), indent=2) + "\n")
    result = run_verifier(r3_case, producer, tmp_path / "report", r4_dir(tmp_path))
    assert result.returncode != 0 and "INTEGRITY_FAILURE" in result.stderr
