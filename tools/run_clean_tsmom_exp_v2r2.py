"""Synthetic-only R2 producer CLI."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom_exp_v2r2 import canonical_bytes, produce, sha256_bytes
from tools.verify_clean_tsmom_exp_v2r2_contract import verify

NAMES = ("main_panel", "main_signals", "main_v1_weights", "main_v2_weights", "main_funding_assignments", "main_funding_returns", "main_turnover", "main_costs", "main_equity_usd", "main_equity_normalized", "main_metrics", "tail_metrics", "benchmark_outputs", "controls", "classifications", "comparison", "final_liquidation")
def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--contract-dir", type=Path, required=True); ap.add_argument("--binding-dir", type=Path, required=True); ap.add_argument("--semantics-dir", type=Path, required=True); ap.add_argument("--source-root", type=Path, required=True); ap.add_argument("--output-dir", type=Path, required=True); a = ap.parse_args()
    verify(a.semantics_dir)
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError("output directory must be empty")
    a.output_dir.mkdir(parents=True, exist_ok=True)
    result = produce(a.source_root); entries = {}
    for name in NAMES:
        b = canonical_bytes(result[name]); (a.output_dir / f"{name}.json").write_bytes(b); entries[f"{name}.json"] = {"sha256": sha256_bytes(b), "bytes": len(b)}
    (a.output_dir / "artifact_manifest.json").write_bytes(canonical_bytes({"schema": "clean-tsmom-exp-v2r2-artifacts-v1", "files": entries}))
    print("CLEAN_TSMOM_EXP_V2R2_PRODUCER_PASS"); return 0
if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc: print(f"ERROR: {exc}", file=sys.stderr); raise SystemExit(1)
