import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_launch_contract_requalification_v0"


def canonical_digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def load(name):
    return json.loads((PHASE / name).read_text(encoding="utf-8"))


def test_requalified_contract_digest_is_recomputable_and_candidate_is_not_accepted():
    contract = load("evidence/contract.json")
    digests = load("evidence/digests.json")
    assert canonical_digest(contract["qualifiedContract"]) == contract["qualifiedContractDigest"]
    assert contract["qualifiedContractDigest"] == "e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82"
    assert digests["candidateMatch"] is True
    assert digests["candidateDigest"] != digests["qualifiedContractDigest"]


def test_physical_contract_binds_exact_runtime_and_governed_repairs():
    contract = load("evidence/contract.json")
    physical = contract["components"]["launchPolicy"]["physicalLaunch"]
    assert physical["source"]["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert physical["source"]["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert physical["toolchain"]["actualPackageManager"] == "11.7.0"
    assert physical["toolchain"]["lockfileDigest"] == "f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea"
    assert [patch["digest"] for patch in physical["governedPatches"]] == [
        "f89bf5833956f3c4202ca88a9285e39658976b29605fc1b63b7c62ebdd07fcb3",
        "2b8277bf13e077651046e2527dc7aa092c3c9669cedc61eac1f742d9364a17e3",
    ]
    assert physical["build"]["entrypointDigest"] == "c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62"


def test_historical_contract_is_preserved_and_registry_has_no_active_project():
    contract = load("evidence/contract.json")
    qualification = load("qualification.json")
    assert contract["predecessor"]["historicalQualifiedContractDigest"] == "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa"
    assert contract["predecessor"]["historicalContractPreserved"] is True
    assert qualification["active_project_after"] == "NONE"

    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    record = projects["DSH_STAGE_A_V1R3R2_LAUNCH_CONTRACT_REQUALIFICATION_V0"]
    assert record["state"] == "CLOSED_PASS"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["active_project_after_closure"] == "NONE"
    assert record["stage_b_authorized"] is False
    assert record["qnty_runtime_authority"] == "NONE"


def test_authority_firewall_has_no_secret_provider_claim_or_downstream_authority():
    firewall = load("evidence/contract.json")["components"]["launchPolicy"]["authorityFirewall"]
    assert firewall == {
        "liveExecutionAuthorized": False,
        "claimAuthorized": False,
        "realSecretReadAuthorized": False,
        "realProviderIoAuthorized": False,
        "stageBAuthorized": False,
        "qntyRuntimeAuthority": "NONE",
        "scientificExecutionAuthorized": False,
        "tradingAuthority": "NONE",
        "capitalAuthority": "NONE",
        "promotionAuthority": "NONE",
        "activeProjectAfterClosure": "NONE",
    }
