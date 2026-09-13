"""Real-source-capable EXP_V2 R3 producer."""
from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom_exp_v2r3 import produce, canonical_bytes
NAMES=("main_panel","main_signals","main_v1_weights","main_v2_weights","main_funding_assignments","main_funding_returns","main_turnover","main_costs","main_equity_usd","main_equity_normalized","main_metrics","tail_metrics","benchmark_outputs","controls","classifications","comparison","final_liquidation")
def main():
    ap=argparse.ArgumentParser()
    for n in ("contract-dir","binding-dir","semantics-dir","implementation-dir","source-root","output-dir"): ap.add_argument("--"+n,dest=n.replace("-","_"),type=Path,required=True)
    a=ap.parse_args()
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError("output directory must be empty")
    result=produce(a.contract_dir,a.binding_dir,a.semantics_dir,a.implementation_dir,a.source_root); a.output_dir.mkdir(parents=True,exist_ok=True); entries={}
    for n in NAMES:
        b=canonical_bytes(result[n]); (a.output_dir/(n+".json")).write_bytes(b); entries[n+".json"]={"sha256":hashlib.sha256(b).hexdigest(),"bytes":len(b)}
    (a.output_dir/"artifact_manifest.json").write_bytes(canonical_bytes({"schema":"clean-tsmom-exp-v2r3-artifacts-v1","files":entries})); print("CLEAN_TSMOM_EXP_V2R3_PRODUCER_PASS")
if __name__=="__main__":
    try: main()
    except Exception as e: print("ERROR: "+str(e),file=sys.stderr); raise SystemExit(1)
