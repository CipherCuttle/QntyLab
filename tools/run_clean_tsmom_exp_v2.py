"""Synthetic-capable deterministic producer CLI; never performs network I/O."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom_exp_v2 import canonical_bytes, produce, sha256_bytes
from tools.verify_clean_tsmom_v2_contract import verify

ARTIFACTS = ("panel", "signals", "v1_weights", "v2_weights", "funding_assignments", "funding_returns", "turnover", "costs", "equity", "controls", "diagnostics", "metrics", "classifications", "final_liquidation")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()): raise ValueError("output directory must be empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    verify(args.experiment_dir / "experiments" / "clean_tsmom" / "v2" if (args.experiment_dir / "experiments" / "clean_tsmom" / "v2").exists() else args.experiment_dir)
    manifest = args.experiment_dir / "data" / "manifests" / "clean-tsmom-v1-source-manifest.json"
    synthetic = (args.experiment_dir / "SYNTHETIC_FIXTURE").exists()
    if not synthetic:
        frozen = json.loads((args.experiment_dir / "source_manifest.json").read_text())
        if not manifest.exists() or hashlib.sha256(manifest.read_bytes()).hexdigest() != frozen["source_manifest_sha256"]: raise ValueError("retained source manifest identity mismatch")
    result = produce(args.experiment_dir)
    entries = {}
    for name in ARTIFACTS:
        payload = canonical_bytes(result[name]); path = args.output_dir / f"{name}.json"; path.write_bytes(payload); entries[path.name] = {"sha256": sha256_bytes(payload), "bytes": len(payload)}
    manifest_bytes = canonical_bytes({"schema": "clean-tsmom-exp-v2-artifacts-v1", "files": entries})
    (args.output_dir / "artifact_manifest.json").write_bytes(manifest_bytes)
    print("CLEAN_TSMOM_EXP_V2_PRODUCER_PASS")
    return 0
if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc: print(f"ERROR: {exc}", file=sys.stderr); raise SystemExit(1)
