import ast
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify_clean_tsmom_exp_v2r1_source_binding import EXPECTED_SYMBOLS, canonical_bytes, verify_source_binding

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "experiments/clean_tsmom/v2"


def _bundle(tmp_path: Path):
    source = tmp_path / "source"; raw = source / "data/raw"; raw.mkdir(parents=True)
    entries = []
    for symbol in EXPECTED_SYMBOLS:
        for kind, name, count, header in (("hourly", f"{symbol}-perp-1h.csv", 3672, ("timestamp", "open", "high", "low", "close", "volume")), ("funding", f"{symbol}-funding.csv", 459, ("timestamp", "funding_interval_hours", "funding_rate"))):
            with (raw / name).open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh); writer.writerow(header)
                for i in range(count):
                    writer.writerow((i * 3_600_000, 1, 1, 1, 1, 1) if kind == "hourly" else (i * 28_800_000, 8, 0.0))
            payload = (raw / name).read_bytes()
            entries.append({"relative_path": f"data/raw/{name}", "symbol": symbol, "kind": kind, "sha256": hashlib.sha256(payload).hexdigest(), "byte_count": len(payload), "row_count": count, "period_start": "2026-03-01T00:00:00Z", "period_end": "2026-08-01T00:00:00Z"})
    manifest = {"MATIC_present": False, "POL_present": False, "canonical_v1_source_manifest_sha256": "8605c6675be20510691f9ed840455de59acb0536c19b1a8fc7386606b3e2470a", "contract_revision": "SOURCE_BINDING_R1", "execution_freeze_commit": "d8319e261761d899289497526bd6ad788ec3ab80", "experiment": "EXP_V2", "files": entries, "funding_file_count": 9, "hourly_file_count": 9, "market_data_network_attempts": 0, "recovery_worktree_head": "f74fd12a4b8180539e62e8e2a846a63a880f9751", "schema_version": "clean-tsmom-exp-v2r1-source-bundle-v1", "scientific_contract_commit": "9a5396ba0aa9403f324ac70e003208ec9ff1ce47", "source_file_count": 18, "symbols": EXPECTED_SYMBOLS}
    binding = {"experiment": "EXP_V2", "contract_revision": "SOURCE_BINDING_R1", "scientific_contract_dir": "experiments/clean_tsmom/v2", "scientific_contract_commit": "9a5396ba0aa9403f324ac70e003208ec9ff1ce47", "execution_parent_commit": "d8319e261761d899289497526bd6ad788ec3ab80", "source_bundle_manifest_sha256": hashlib.sha256(canonical_bytes(manifest)).hexdigest(), "expected_symbols": EXPECTED_SYMBOLS, "expected_source_files": 18, "hourly_files": 9, "funding_files": 9, "source_root_is_external": True, "network_retrieval_allowed": False, "expanded_checkout_datasets_allowed": False, "amendment": "This amendment changes source discovery and authentication only. It does not change the analyzed bytes or any scientific strategy semantics."}
    binding_dir = tmp_path / "binding"; binding_dir.mkdir()
    (binding_dir / "source_bundle_manifest.json").write_bytes(canonical_bytes(manifest)); (binding_dir / "source_bundle_manifest.sha256").write_text(hashlib.sha256((binding_dir / "source_bundle_manifest.json").read_bytes()).hexdigest() + "\n")
    (binding_dir / "source_binding_r1.json").write_bytes(canonical_bytes(binding)); (binding_dir / "source_binding_r1.sha256").write_text(hashlib.sha256((binding_dir / "source_binding_r1.json").read_bytes()).hexdigest() + "\n")
    return source, binding_dir


def _run(tmp_path, source, binding, contract=CONTRACT):
    return verify_source_binding(contract, binding, source)


def test_external_nine_symbol_bundle_passes(tmp_path):
    source, binding = _bundle(tmp_path); result = _run(tmp_path, source, binding)
    assert result["source_files_present"] == 18 and result["all_symbol_sets_equal"] == 1


@pytest.mark.parametrize("mutation", ["avax_only", "one_symbol_manifest", "contract_manifest_mismatch", "matic", "pol"])
def test_symbol_set_rejections(tmp_path, mutation):
    source, binding = _bundle(tmp_path); path = binding / "source_bundle_manifest.json"; obj = json.loads(path.read_bytes())
    if mutation == "avax_only": obj["symbols"] = ["AVAXUSDT"]
    elif mutation == "one_symbol_manifest": obj["symbols"] = ["BTCUSDT"]
    elif mutation == "contract_manifest_mismatch": obj["symbols"] = EXPECTED_SYMBOLS[:-1]
    elif mutation == "matic": obj["symbols"] = EXPECTED_SYMBOLS + ["MATICUSDT"]
    else: obj["symbols"] = EXPECTED_SYMBOLS + ["POLUSDT"]
    path.write_bytes(canonical_bytes(obj)); (binding / "source_bundle_manifest.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


@pytest.mark.parametrize("kind", ["hourly", "funding"])
def test_missing_source_file_rejected(tmp_path, kind):
    source, binding = _bundle(tmp_path); (source / "data/raw" / f"BTCUSDT-{'perp-1h' if kind == 'hourly' else 'funding'}.csv").unlink()
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


def test_additional_source_file_rejected(tmp_path):
    source, binding = _bundle(tmp_path); (source / "data/raw" / "MATICUSDT-funding.csv").write_text("x\n")
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


def test_altered_recovered_hash_rejected(tmp_path):
    source, binding = _bundle(tmp_path); p = source / "data/raw/BTCUSDT-perp-1h.csv"; p.write_bytes(p.read_bytes() + b"x")
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


def test_expanded_checkout_substitution_rejected(tmp_path):
    source, binding = _bundle(tmp_path); p = source / "data/raw/BTCUSDT-perp-1h.csv"; p.write_bytes(Path("/home/swirky/DevHub/repos/QntyLab/data/raw/BTCUSDT-perp-1h.csv").read_bytes())
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


def test_bundle_manifest_digest_mismatch_rejected(tmp_path):
    source, binding = _bundle(tmp_path); (binding / "source_bundle_manifest.sha256").write_text("0" * 64 + "\n")
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


def test_absolute_source_path_in_manifest_rejected(tmp_path):
    source, binding = _bundle(tmp_path); path = binding / "source_bundle_manifest.json"; obj = json.loads(path.read_bytes()); obj["files"][0]["relative_path"] = str(source / "data/raw/BTCUSDT-perp-1h.csv"); path.write_bytes(canonical_bytes(obj)); (binding / "source_bundle_manifest.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    with pytest.raises(ValueError): _run(tmp_path, source, binding)


def test_nonempty_output_directory_rejected(tmp_path):
    source, binding = _bundle(tmp_path); output = tmp_path / "out"; output.mkdir(); (output / "existing").write_text("x")
    result = subprocess.run([sys.executable, "tools/run_clean_tsmom_exp_v2r1.py", "--contract-dir", str(CONTRACT), "--binding-dir", str(binding), "--source-root", str(source), "--output-dir", str(output)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0 and "empty" in result.stdout


def test_producer_requires_explicit_source_root_and_does_not_use_checkout():
    source = (ROOT / "tools/run_clean_tsmom_exp_v2r1.py").read_text()
    assert "--source-root" in source and 'source_root / "data" / "raw"' in source


def test_source_root_and_contract_root_are_separate(tmp_path):
    source, binding = _bundle(tmp_path)
    with pytest.raises(ValueError): _run(tmp_path, CONTRACT, binding)


def test_independent_verifier_has_no_producer_import_or_invocation():
    tree = ast.parse((ROOT / "tools/verify_clean_tsmom_exp_v2r1_results.py").read_text())
    assert all(not (isinstance(n, ast.ImportFrom) and (n.module or "").endswith("clean_tsmom_exp_v2")) for n in ast.walk(tree))
    assert "run_clean_tsmom_exp_v2.py" not in (ROOT / "tools/verify_clean_tsmom_exp_v2r1_results.py").read_text()
