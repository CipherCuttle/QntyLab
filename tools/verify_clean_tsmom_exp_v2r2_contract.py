"""Fail-closed verifier for additive R2 normative artifacts."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

FILES = ("execution_semantics_r2.json", "metric_contract_r2.json", "benchmark_contract_r2.json", "classification_policy_r2.json", "artifact_contract_r2.json", "implementation_manifest_r2.json")
def verify(path: Path) -> None:
    for name in FILES:
        p = path / name; side = path / name.replace(".json", ".sha256")
        if not p.is_file() or not side.is_file(): raise ValueError(f"missing R2 artifact: {name}")
        if hashlib.sha256(p.read_bytes()).hexdigest() != side.read_text().split()[0]: raise ValueError(f"checksum mismatch: {name}")
        obj = json.loads(p.read_bytes())
        if json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) .encode() + b"\n" != p.read_bytes(): raise ValueError(f"noncanonical JSON: {name}")
    execution = json.loads((path / FILES[0]).read_bytes()); metric = json.loads((path / FILES[1]).read_bytes()); bench = json.loads((path / FILES[2]).read_bytes()); policy = json.loads((path / FILES[3]).read_bytes())
    if execution["same_bar_execution"] or not execution["t_plus_1_execution"]: raise ValueError("execution semantics are not causal")
    if metric["periods_per_year"] != 1095 or metric["standard_deviation_ddof"] != 0: raise ValueError("metric constants mismatch")
    if len(bench["benchmarks"]) != 3 or policy["status"] != "PROSPECTIVE_EXP_V2_POLICY": raise ValueError("R2 benchmark/classification contract mismatch")

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--semantics-dir", type=Path, required=True); a = ap.parse_args(); verify(a.semantics_dir); print("CLEAN_TSMOM_EXP_V2R2_CONTRACT_PASS"); return 0
if __name__ == "__main__": raise SystemExit(main())
