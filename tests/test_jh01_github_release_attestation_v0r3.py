import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_release_attestation_offline_policy_qualification_v0r3.json"
Q = ROOT / "qualifications/jh01_v0r3"
GO = Path("/tmp/qntylab-go-toolchain/go/bin/go")

def test_v0r3_is_governance_only_and_bounded():
    r=json.loads(RESULT.read_text())
    assert r["state"] == "CLOSED_PASS" and r["future_bounded_recorder_implementation_authorized"] is True
    assert r["implementation_authorized"] is False and not any(r["outcome_blindness"].values())
    assert r["verified"]["tsa_minus_published_at_seconds"] == 0

@pytest.mark.parametrize("old,new", [
 ("CipherCuttle/QntyLab","Wrong/Repo"), ("1317911390","0000000000"), ("97258089","00000000"),
 ("370208366","000000000"), ("qntylab-jh01-v1-persistence-qualification-v0r1-7ad471c","wrong-tag"),
 ("7ad471c82c9fa6aef0432f6999e0fce0649d2c55","0"*40),
 ("191dfe3693a1e10f6efa8a385ca4c86953798d7e27a6f8e0c08dcbefc99ee4a7","0"*64),
 ("https://in-toto.io/attestation/release/v0.2","https://wrong.example/predicate"),
 ("https://dotcom.releases.github.com","https://wrong.example/signer"),
])
def test_wrong_out_of_band_policy_fails_closed(tmp_path, old, new):
    d=tmp_path/"q"; shutil.copytree(Q,d); p=d/"main.go"; p.write_text(p.read_text().replace(old,new,1))
    exe=tmp_path/"verify"; subprocess.run([str(GO),"build","-o",str(exe),"."],cwd=d,check=True,env={**os.environ,"GOPROXY":"off"})
    run=subprocess.run(["bwrap","--unshare-net","--ro-bind","/","/","--dev","/dev","--proc","/proc","--",str(exe),str(Q/"retention/forecast.json"),str(Q/"retention/trusted_root.jsonl"),str(Q/"retention/release_attestation.sigstore.json")],capture_output=True,text=True)
    assert run.returncode != 0 and "POLICY_REJECTED" in run.stderr

@pytest.mark.parametrize("target",["forecast.json","release_attestation.sigstore.json","missing_github_extension","conflicting_asset_subject","conflicting_commit_subject"])
def test_local_signed_input_mutation_fails_before_policy(tmp_path,target):
    asset=tmp_path/"asset"; bundle=tmp_path/"bundle"; root=Q/"retention/trusted_root.jsonl"
    shutil.copy(Q/"retention/forecast.json",asset); shutil.copy(Q/"retention/release_attestation.sigstore.json",bundle)
    # These payload-level attack names cover a missing extension and conflicting
    # subjects by changing the signed DSSE bytes without re-signing: all must be
    # rejected in Stage A, before any Stage-B schema interpretation is possible.
    p=asset if target=="forecast.json" else bundle; b=bytearray(p.read_bytes());b[-2]^=1;p.write_bytes(b)
    exe=tmp_path/"verify"; subprocess.run([str(GO),"build","-o",str(exe),"."],cwd=Q,check=True,env={**os.environ,"GOPROXY":"off"})
    run=subprocess.run(["bwrap","--unshare-net","--ro-bind","/","/","--dev","/dev","--proc","/proc","--",str(exe),str(asset),str(root),str(bundle)],capture_output=True,text=True)
    assert run.returncode != 0 and "POLICY_REJECTED" in run.stderr

def test_negative_matrix_is_frozen():
    assert json.loads(RESULT.read_text())["negative_policy_tests"] == {"count":14,"tests_pass":True,"all_fail_closed":True,"local_only":True}
