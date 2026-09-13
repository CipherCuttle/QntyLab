from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT")
START = 1776902400000
END = 1785542400000
HOUR = 3_600_000
H8 = 8 * HOUR


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sidecar(path: Path):
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def _write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _copy_contracts(tmp_path):
    contract = tmp_path / "contract"; binding = tmp_path / "binding"; semantics = tmp_path / "semantics"; implementation = tmp_path / "implementation"
    shutil.copytree(ROOT / "experiments/clean_tsmom/v2", contract)
    shutil.copytree(ROOT / "experiments/clean_tsmom/v2r2", semantics)
    shutil.copytree(ROOT / "experiments/clean_tsmom/v2r3", implementation)
    binding.mkdir()
    return contract, binding, semantics, implementation


def _build_bundle(tmp_path):
    source = tmp_path / "bundle"; raw = source / "data/raw"; raw.mkdir(parents=True)
    entries = []
    bars = 500; first = START - 120 * H8
    for si, symbol in enumerate(SYMBOLS):
        hourly = []
        base = 80.0 + 17.0 * si
        for i in range(bars * 8):
            t = i // 8
            import math
            close = base * (1.0 + 0.00001 * i) * math.exp(0.045 * math.sin(2 * math.pi * t / 60.0) + 0.00003 * si * t)
            ts = first + i * HOUR
            hourly.append((ts, close * .999, close * 1.001, close * .998, close, 1000 + si))
        hp = raw / f"{symbol}-perp-1h.csv"; _write_csv(hp, ("timestamp", "open", "high", "low", "close", "volume"), hourly)
        entries.append({"relative_path": f"data/raw/{hp.name}", "symbol": symbol, "kind": "hourly", "sha256": hashlib.sha256(hp.read_bytes()).hexdigest(), "byte_count": hp.stat().st_size, "row_count": len(hourly)})
        funding = [(first + (i + 1) * H8, 8, ((-1) ** (i + si)) * (0.00001 + si * 0.000001)) for i in range(bars - 1)]
        fp = raw / f"{symbol}-funding.csv"; _write_csv(fp, ("timestamp", "funding_interval_hours", "funding_rate"), funding)
        entries.append({"relative_path": f"data/raw/{fp.name}", "symbol": symbol, "kind": "funding", "sha256": hashlib.sha256(fp.read_bytes()).hexdigest(), "byte_count": fp.stat().st_size, "row_count": len(funding)})
    manifest = {"MATIC_present": False, "POL_present": False, "contract_revision": "SOURCE_BINDING_R1", "experiment": "EXP_V2", "files": entries, "funding_file_count": 9, "hourly_file_count": 9, "market_data_network_attempts": 0, "schema_version": "clean-tsmom-exp-v2r1-source-bundle-v1", "source_file_count": 18, "symbols": list(SYMBOLS)}
    mp = source / "source_bundle_manifest.json"; mp.write_bytes(canonical(manifest)); sidecar(mp)
    contract, binding, semantics, implementation = _copy_contracts(tmp_path)
    bm = binding / "source_bundle_manifest.json"; bm.write_bytes(mp.read_bytes()); sidecar(bm)
    binding_obj = {"experiment": "EXP_V2", "contract_revision": "SOURCE_BINDING_R1", "scientific_contract_dir": "experiments/clean_tsmom/v2", "source_bundle_manifest_sha256": hashlib.sha256(bm.read_bytes()).hexdigest(), "expected_symbols": list(SYMBOLS), "expected_source_files": 18, "hourly_files": 9, "funding_files": 9, "source_root_is_external": True, "network_retrieval_allowed": False, "expanded_checkout_datasets_allowed": False}
    bp = binding / "source_binding_r1.json"; bp.write_bytes(canonical(binding_obj)); sidecar(bp)
    return {"source": source, "contract": contract, "binding": binding, "semantics": semantics, "implementation": implementation}


@pytest.fixture
def r3_case(tmp_path):
    return _build_bundle(tmp_path)


def run_producer(case, output, *extra):
    cmd = [sys.executable, "tools/run_clean_tsmom_exp_v2r3.py", "--contract-dir", str(case["contract"]), "--binding-dir", str(case["binding"]), "--semantics-dir", str(case["semantics"]), "--implementation-dir", str(case["implementation"]), "--source-root", str(case["source"]), "--output-dir", str(output), *extra]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def run_verifier(case, producer, output):
    cmd = [sys.executable, "tools/verify_clean_tsmom_exp_v2r3_results.py", "--contract-dir", str(case["contract"]), "--binding-dir", str(case["binding"]), "--semantics-dir", str(case["semantics"]), "--implementation-dir", str(case["implementation"]), "--source-root", str(case["source"]), "--producer-root", str(producer), "--output-dir", str(output)]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
