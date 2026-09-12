"""Read-only EXP_V2 SOURCE_BINDING_R1 source identity verifier."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT"]
EXPECTED_FILES = {f"{s}-perp-1h.csv": (s, "hourly", 3672) for s in EXPECTED_SYMBOLS}
EXPECTED_FILES.update({f"{s}-funding.csv": (s, "funding", 459) for s in EXPECTED_SYMBOLS})


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sidecar(path: Path) -> None:
    expected = path.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"checksum mismatch: {path.name}")


def _reject_absolute_strings(value: object) -> None:
    if isinstance(value, str) and (value.startswith("/") or value.startswith("~") or "://" in value):
        raise ValueError("absolute or external path embedded in committed manifest")
    if isinstance(value, dict):
        for item in value.values():
            _reject_absolute_strings(item)
    elif isinstance(value, list):
        for item in value:
            _reject_absolute_strings(item)


def _rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1


def verify_source_binding(contract_dir: Path, binding_dir: Path, source_root: Path) -> dict[str, object]:
    from tools.verify_clean_tsmom_v2_contract import verify as verify_contract

    verify_contract(contract_dir)
    required = ("source_binding_r1.json", "source_binding_r1.sha256", "source_bundle_manifest.json", "source_bundle_manifest.sha256")
    if any(not (binding_dir / name).is_file() for name in required):
        raise ValueError("missing R1 binding artifact")
    _sidecar(binding_dir / "source_binding_r1.json")
    _sidecar(binding_dir / "source_bundle_manifest.json")
    binding = json.loads((binding_dir / "source_binding_r1.json").read_bytes())
    manifest_path = binding_dir / "source_bundle_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest_bytes != canonical_bytes(manifest):
        raise ValueError("bundle manifest is not canonical JSON")
    if binding["experiment"] != "EXP_V2" or binding["contract_revision"] != "SOURCE_BINDING_R1":
        raise ValueError("incorrect R1 identity")
    if binding["source_bundle_manifest_sha256"] != sha256(manifest_path):
        raise ValueError("binding and referenced manifest digest disagree")
    contract = json.loads((contract_dir / "source_contract.json").read_bytes())
    contract_symbols = contract["universe"]
    binding_symbols = binding["expected_symbols"]
    manifest_symbols = manifest["symbols"]
    if contract_symbols != EXPECTED_SYMBOLS or binding_symbols != EXPECTED_SYMBOLS or manifest_symbols != EXPECTED_SYMBOLS:
        raise ValueError("contract, binding, and manifest symbol sets differ")
    if set(contract_symbols) != set(binding_symbols) or set(contract_symbols) != set(manifest_symbols):
        raise ValueError("contract, binding, and manifest symbol sets differ")
    if any(symbol in contract_symbols for symbol in ("MATICUSDT", "POLUSDT")):
        raise ValueError("forbidden symbol present")
    _reject_absolute_strings(manifest)
    if manifest.get("source_file_count") != 18 or manifest.get("hourly_file_count") != 9 or manifest.get("funding_file_count") != 9:
        raise ValueError("incorrect source file counts")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 18:
        raise ValueError("manifest does not contain exactly 18 files")
    raw = source_root / "data" / "raw"
    if not raw.is_dir():
        raise ValueError("source root must contain data/raw")
    actual_names = {p.name for p in raw.iterdir() if p.is_file()}
    if actual_names != set(EXPECTED_FILES):
        raise ValueError("source root contains missing or additional files")
    seen: set[str] = set()
    mismatches = 0
    hourly_rows: list[int] = []
    funding_rows: list[int] = []
    for entry in files:
        rel = entry.get("relative_path")
        if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise ValueError("manifest path is not relative")
        if rel in seen:
            raise ValueError("duplicate manifest path")
        seen.add(rel)
        name = Path(rel).name
        if Path(rel).parent != Path("data/raw") or name not in EXPECTED_FILES:
            raise ValueError("manifest contains unexpected source file")
        symbol, kind, expected_rows = EXPECTED_FILES[name]
        if entry.get("symbol") != symbol or entry.get("kind") != kind:
            raise ValueError("manifest file metadata mismatch")
        path = source_root / rel
        actual_hash = sha256(path)
        actual_bytes = path.stat().st_size
        actual_rows = _rows(path)
        if actual_hash != entry.get("sha256") or actual_bytes != entry.get("byte_count") or actual_rows != entry.get("row_count"):
            mismatches += 1
        if actual_rows != expected_rows:
            mismatches += 1
        (hourly_rows if kind == "hourly" else funding_rows).append(actual_rows)
    if seen != {f"data/raw/{name}" for name in EXPECTED_FILES} or mismatches:
        raise ValueError(f"source hash or row mismatch: {mismatches}")
    result = {
        "source_files_expected": 18,
        "source_files_present": 18,
        "source_hash_mismatches": 0,
        "contract_symbols": len(contract_symbols),
        "binding_symbols": len(binding_symbols),
        "manifest_symbols": len(manifest_symbols),
        "all_symbol_sets_equal": 1,
        "hourly_rows_per_symbol": sorted(set(hourly_rows)),
        "funding_rows_per_symbol": sorted(set(funding_rows)),
        "MATIC_present": 0,
        "POL_present": 0,
        "strategy_evaluation_attempts": 0,
        "corrected_metrics_observed": 0,
        "market_data_network_attempts": 0,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-dir", type=Path, required=True)
    parser.add_argument("--binding-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    result = verify_source_binding(args.contract_dir, args.binding_dir, args.source_root)
    print("CLEAN_TSMOM_EXP_V2_R1_SOURCE_BINDING_PASS")
    for key, value in result.items():
        print(f"{key}={json.dumps(value, separators=(',', ':'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
