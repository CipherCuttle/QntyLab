"""R5 producer CLI.  It is intended for deterministic artificial bundles only."""
from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom_exp_v2r5 import build, canonical_bytes

NAMES = ("interval_ledgers", "equity_artifacts", "metrics", "tail_metrics", "controls", "comparison", "signals_and_weights")

def main():
    ap = argparse.ArgumentParser()
    for n in ("contract-dir", "binding-dir", "semantics-dir", "implementation-dir", "verification-dir", "accounting-dir", "source-root", "output-dir"):
        ap.add_argument("--" + n, dest=n.replace("-", "_"), type=Path, required=True)
    a = ap.parse_args()
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError("output directory must be empty")
    if a.source_root.resolve().as_posix().startswith("/home/swirky/DevHub/evidence/"):
        raise ValueError("R5 producer refuses the real external source bundle")
    result = build(a.source_root); a.output_dir.mkdir(parents=True, exist_ok=True); files = {}
    for name in NAMES:
        data = canonical_bytes(result[name]); path = a.output_dir / (name + ".json"); path.write_bytes(data); files[path.name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    manifest = canonical_bytes({"schema": "clean-tsmom-exp-v2r5-artifacts-v1", "files": files})
    (a.output_dir / "artifact_manifest.json").write_bytes(manifest)
    print("CLEAN_TSMOM_EXP_V2R5_PRODUCER_PASS")

if __name__ == "__main__":
    try: main()
    except Exception as exc: print("ERROR: " + str(exc), file=sys.stderr); raise SystemExit(1)
