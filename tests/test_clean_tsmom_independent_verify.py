import json
import shutil
from pathlib import Path

import pytest

from tools.verify_clean_tsmom_v1_results import build_panel, validate_frozen_artifacts, verify


ROOT = Path(__file__).parents[1]


def test_independent_v1_metrics_match_submitted_artifact():
    report = verify(ROOT)
    assert report["timestamps"] == 459
    assert report["main_bars"] == 300
    assert report["tail_bars"] == 129
    for key, fields in report["reports"].items():
        if key.startswith("CLEAN_V2"):
            continue
        assert all(diff <= 1e-12 for _, _, diff in fields.values())


def test_independent_verifier_exposes_v2_lookahead_mismatch():
    report = verify(ROOT)
    assert report["reports"]["CLEAN_V2_base"]["net_return"][2] > 1e-12
    assert report["reports"]["CLEAN_V2_base"]["sharpe"][2] > 1e-12


def test_independent_verifier_rejects_source_mutation(tmp_path):
    source = ROOT / "data/raw/BTCUSDT-perp-1h.csv"
    target = tmp_path / "data/raw/BTCUSDT-perp-1h.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        build_panel(tmp_path)


def test_result_artifact_has_no_nonfinite_json_constants():
    text = (ROOT / "experiments/clean_tsmom/v1/results_v1.json").read_text()
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(AssertionError(value)))


def _copy_identity_inputs(tmp_path):
    paths = [
        "experiments/clean_tsmom/v1/source_contract.json",
        "experiments/clean_tsmom/v1/source_contract.sha256",
        "experiments/clean_tsmom/v1/v1_equal_weight.json",
        "experiments/clean_tsmom/v1/v1_equal_weight.sha256",
        "experiments/clean_tsmom/v1/v2_inverse_vol.json",
        "experiments/clean_tsmom/v1/v2_inverse_vol.sha256",
        "experiments/clean_tsmom/v1/evaluation_v1.json",
        "experiments/clean_tsmom/v1/evaluation_v1.sha256",
        "experiments/clean_tsmom/v1/results_v1.json",
    ]
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def test_verifier_rejects_mutated_frozen_specification(tmp_path):
    _copy_identity_inputs(tmp_path)
    path = tmp_path / "experiments/clean_tsmom/v1/v2_inverse_vol.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="frozen specification hash mismatch"):
        validate_frozen_artifacts(tmp_path)


def test_verifier_rejects_mismatched_specification_sidecar(tmp_path):
    _copy_identity_inputs(tmp_path)
    path = tmp_path / "experiments/clean_tsmom/v1/evaluation_v1.sha256"
    path.write_text("0" * 64 + "  evaluation_v1.json\n")
    with pytest.raises(ValueError, match="frozen specification sidecar hash mismatch"):
        validate_frozen_artifacts(tmp_path)


def test_verifier_rejects_mutated_original_result_artifact(tmp_path):
    _copy_identity_inputs(tmp_path)
    path = tmp_path / "experiments/clean_tsmom/v1/results_v1.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="original result artifact hash mismatch"):
        validate_frozen_artifacts(tmp_path)


def test_verifier_rejects_mismatched_expected_result_digest(tmp_path):
    _copy_identity_inputs(tmp_path)
    with pytest.raises(ValueError, match="original result artifact hash mismatch"):
        validate_frozen_artifacts(tmp_path, expected_result_sha256="0" * 64)
