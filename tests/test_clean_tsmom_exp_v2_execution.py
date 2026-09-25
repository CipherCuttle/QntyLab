import csv, json, subprocess, sys
from pathlib import Path
from qntylab.clean_tsmom import SYMBOLS
from qntylab.clean_tsmom_exp_v2 import produce

def fixture(tmp_path):
    root=tmp_path/"fixture"; (root/"data/raw").mkdir(parents=True); (root/"data/manifests").mkdir()
    (root/"SYNTHETIC_FIXTURE").write_text("fixture\n")
    contract=Path(__file__).parents[1]/"experiments/clean_tsmom/v2"
    for name in ("README.md","source_contract.json","source_contract.sha256","v1_equal_weight.json","v1_equal_weight.sha256","v2_inverse_vol.json","v2_inverse_vol.sha256","evaluation_v2.json","evaluation_v2.sha256","source_manifest.json","source_manifest.sha256"):
        (root/name).write_bytes((contract/name).read_bytes())
    for s_i,s in enumerate(SYMBOLS):
        with (root/"data/raw"/f"{s}-perp-1h.csv").open("w",newline="") as fh:
            w=csv.writer(fh); w.writerow(("timestamp","open","high","low","close","volume"))
            for h in range(8*125):
                p=100+s_i+h*(0.01+s_i*0.001); w.writerow((h*3600000,p,p,p,p,1))
        with (root/"data/raw"/f"{s}-funding.csv").open("w",newline="") as fh:
            w=csv.writer(fh); w.writerow(("timestamp","funding_interval_hours","funding_rate")); w.writerows((i*8*3600000,8,0.0001*(-1 if i%2 else 1)) for i in range(125))
    return root

def test_synthetic_producer_has_causal_weights_and_controls(tmp_path):
    result=produce(fixture(tmp_path)); assert result["controls"]["future_close_consumption"] is False; assert result["controls"]["final_liquidation_charged"] is True
    assert len(result["v2_weights"]) == 125

def test_cli_determinism_and_independent_full_agreement(tmp_path):
    root=fixture(tmp_path); a=tmp_path/"a"; b=tmp_path/"b"; va=tmp_path/"va"
    cli=[sys.executable,"tools/run_clean_tsmom_exp_v2.py","--experiment-dir",str(root),"--output-dir"]
    subprocess.run(cli+[str(a)],cwd=Path(__file__).parents[1],check=True,capture_output=True,text=True)
    subprocess.run(cli+[str(b)],cwd=Path(__file__).parents[1],check=True,capture_output=True,text=True)
    assert sorted(p.relative_to(a) for p in a.rglob("*")) == sorted(p.relative_to(b) for p in b.rglob("*"))
    assert all(p.read_bytes()==(b/p.relative_to(a)).read_bytes() for p in a.rglob("*") if p.is_file())
    subprocess.run([sys.executable,"tools/verify_clean_tsmom_exp_v2_results.py","--experiment-dir",str(root),"--producer-root",str(a),"--output-dir",str(va)],cwd=Path(__file__).parents[1],check=True,capture_output=True,text=True)
