import hashlib
import shutil
import subprocess
import sys

from tests._clean_tsmom_exp_v2r3_fixture import ROOT

def r4_dir(tmp_path):
    out = tmp_path / "verification"
    shutil.copytree(ROOT / "experiments/clean_tsmom/v2r4", out)
    for name in ("independent_verification_r4.json", "implementation_manifest_r4.json"):
        p = out / name
        (out / (p.stem + ".sha256")).write_text(hashlib.sha256(p.read_bytes()).hexdigest() + "\n")
    return out

def run_verifier(case, producer, report, verification):
    return subprocess.run([sys.executable, "tools/verify_clean_tsmom_exp_v2r4_results.py", "--contract-dir", str(case["contract"]), "--binding-dir", str(case["binding"]), "--semantics-dir", str(case["semantics"]), "--implementation-dir", str(case["implementation"]), "--verification-dir", str(verification), "--source-root", str(case["source"]), "--producer-root", str(producer), "--output-dir", str(report)], cwd=ROOT, text=True, capture_output=True)
