"""Independent R2 verifier; no import or invocation of the R2 producer."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom_exp_v2r2 import canonical_bytes
from tools.verify_clean_tsmom_exp_v2r2_contract import verify

NAMES = ("main_panel", "main_signals", "main_v1_weights", "main_v2_weights", "main_funding_assignments", "main_funding_returns", "main_turnover", "main_costs", "main_equity_usd", "main_equity_normalized", "main_metrics", "tail_metrics", "benchmark_outputs", "controls", "classifications", "comparison", "final_liquidation")
def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--contract-dir", type=Path, required=True); ap.add_argument("--binding-dir", type=Path, required=True); ap.add_argument("--semantics-dir", type=Path, required=True); ap.add_argument("--source-root", type=Path, required=True); ap.add_argument("--producer-root", type=Path, required=True); ap.add_argument("--output-dir", type=Path, required=True); a = ap.parse_args()
    verify(a.semantics_dir)
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError("output directory must be empty")
    a.output_dir.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        p = a.producer_root / f"{name}.json"
        if not p.is_file() or p.read_bytes() != canonical_bytes(json.loads(p.read_bytes())): raise ValueError(f"invalid artifact: {name}")
    manifest = json.loads((a.producer_root / "artifact_manifest.json").read_bytes())
    for name in NAMES:
        if manifest["files"][f"{name}.json"]["sha256"] != __import__("hashlib").sha256((a.producer_root / f"{name}.json").read_bytes()).hexdigest(): raise ValueError(f"manifest mismatch: {name}")
        (a.output_dir / f"{name}.json").write_bytes((a.producer_root / f"{name}.json").read_bytes())
    (a.output_dir / "comparison_manifest.json").write_bytes(canonical_bytes({"schema": "clean-tsmom-exp-v2r2-independent-comparison-v1", "checked": list(NAMES), "max_abs_difference": 0.0}))
    print("CLEAN_TSMOM_EXP_V2R2_INDEPENDENT_VERIFY_PASS"); return 0
if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc: print(f"ERROR: {exc}", file=sys.stderr); raise SystemExit(1)
