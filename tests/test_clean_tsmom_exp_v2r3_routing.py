from pathlib import Path

import pytest

from tests._clean_tsmom_exp_v2r3_fixture import ROOT, r3_case, run_producer, sidecar


def test_valid_authenticated_artificial_bundle_passes(r3_case, tmp_path):
    result = run_producer(r3_case, tmp_path / "out")
    assert result.returncode == 0, result.stderr
    assert "CLEAN_TSMOM_EXP_V2R3_PRODUCER_PASS" in result.stdout


@pytest.mark.parametrize("key", ["contract", "binding", "semantics", "implementation"])
def test_required_roots_are_explicit_and_missing_roots_fail(r3_case, tmp_path, key):
    case = dict(r3_case); case[key] = tmp_path / (key + "-missing")
    result = run_producer(case, tmp_path / "out")
    assert result.returncode != 0


@pytest.mark.parametrize("key", ["contract", "binding", "semantics", "implementation"])
def test_altered_contract_or_binding_payload_or_sidecar_fails(r3_case, tmp_path, key):
    case = dict(r3_case); root = case[key]
    payload = next(root.glob("*.json")); payload.write_bytes(payload.read_bytes() + b" ")
    result = run_producer(case, tmp_path / "out")
    assert result.returncode != 0


@pytest.mark.parametrize("mutation", ["manifest_digest", "source_byte", "missing_hourly", "missing_funding", "additional", "matic", "pol"])
def test_source_bundle_hostile_mutations_fail(r3_case, tmp_path, mutation):
    source = r3_case["source"]; raw = source / "data/raw"
    if mutation == "manifest_digest": (source / "source_bundle_manifest.sha256").write_text("0" * 64 + "\n")
    elif mutation == "source_byte": (raw / "BTCUSDT-perp-1h.csv").write_bytes((raw / "BTCUSDT-perp-1h.csv").read_bytes() + b"x")
    elif mutation == "missing_hourly": (raw / "BTCUSDT-perp-1h.csv").unlink()
    elif mutation == "missing_funding": (raw / "BTCUSDT-funding.csv").unlink()
    else:
        name = "MATICUSDT-funding.csv" if mutation == "matic" else "POLUSDT-funding.csv" if mutation == "pol" else "EXTRA-funding.csv"
        (raw / name).write_text("timestamp,funding_interval_hours,funding_rate\n1,8,0\n")
    result = run_producer(r3_case, tmp_path / "out")
    assert result.returncode != 0


def test_checkout_local_substitution_is_rejected(r3_case, tmp_path):
    case = dict(r3_case); case["source"] = ROOT
    result = run_producer(case, tmp_path / "out")
    assert result.returncode != 0


def test_nonempty_output_directory_is_rejected(r3_case, tmp_path):
    output = tmp_path / "out"; output.mkdir(); (output / "existing").write_text("x")
    result = run_producer(r3_case, output)
    assert result.returncode != 0 and "empty" in result.stderr


def test_source_manifest_must_be_bound_to_r1_material(r3_case, tmp_path):
    manifest = r3_case["source"] / "source_bundle_manifest.json"
    manifest.write_bytes(manifest.read_bytes().replace(b'"MATIC_present":false', b'"MATIC_present":true'))
    sidecar(manifest)
    result = run_producer(r3_case, tmp_path / "out")
    assert result.returncode != 0
