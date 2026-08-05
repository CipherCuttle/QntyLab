from __future__ import annotations
import shutil, subprocess, sys
from pathlib import Path
import pytest
from tests._clean_tsmom_exp_v2r3_fixture import _build_bundle

ROOT = Path(__file__).parents[1]

@pytest.fixture
def r5_case(tmp_path):
    case = _build_bundle(tmp_path)
    accounting = tmp_path / "accounting"; shutil.copytree(ROOT / "experiments/clean_tsmom/v2r5", accounting)
    verification = tmp_path / "verification"; verification.mkdir()
    case.update(accounting=accounting, verification=verification)
    return case

def run_producer(case, output):
    cmd = [sys.executable, "tools/run_clean_tsmom_exp_v2r5.py", "--contract-dir", str(case["contract"]), "--binding-dir", str(case["binding"]), "--semantics-dir", str(case["semantics"]), "--implementation-dir", str(case["implementation"]), "--verification-dir", str(case["verification"]), "--accounting-dir", str(case["accounting"]), "--source-root", str(case["source"]), "--output-dir", str(output)]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)

def run_verifier(case, producer, report):
    cmd = [sys.executable, "tools/verify_clean_tsmom_exp_v2r5_results.py", "--contract-dir", str(case["contract"]), "--binding-dir", str(case["binding"]), "--semantics-dir", str(case["semantics"]), "--implementation-dir", str(case["implementation"]), "--verification-dir", str(case["verification"]), "--accounting-dir", str(case["accounting"]), "--source-root", str(case["source"]), "--producer-root", str(producer), "--output-dir", str(report)]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
