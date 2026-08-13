from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_immutable_release_persistence_backend_qualification_v0r2.json"
V0R1 = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_immutable_release_persistence_backend_qualification_v0r1.json"


def result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_v0r1_and_frozen_v1_authority_are_unchanged() -> None:
    value = result()
    prereg = ROOT / value["frozen_v1_authority"]["path"]
    assert value["canonical_merge_lineage"]["contained_in_canonical_master"] is True
    assert value["predecessor_v0r1"] == {"project_id": value["predecessor_v0r1"]["project_id"], "state": "CLOSED_BLOCKED", "reopened": False, "bytes_modified": False}
    assert json.loads(V0R1.read_text(encoding="utf-8"))["state"] == "CLOSED_BLOCKED"
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == value["frozen_v1_authority"]["bytes_sha256"]


def test_retained_release_and_online_release_attestation_are_exact() -> None:
    value = result()
    release, online = value["retained_release"], value["online_reference_verification"]
    assert release["immutable"] is True and release["unchanged"] is True
    assert (release["new_release_created"], release["new_tag_created"], release["existing_release_mutated"]) == (False, False, False)
    assert release["remote_asset_digest"] == "sha256:" + release["asset_sha256"]
    assert (online["release_verify"], online["asset_verify"]) == ("PASS", "PASS")
    assert online["release_predicate_type"] == "https://in-toto.io/attestation/release/v0.2"
    assert online["signed_repository"] == "CipherCuttle/QntyLab"
    assert online["signed_asset_sha256"] == release["asset_sha256"]


def test_timestamp_and_offline_identity_gate_fail_closed() -> None:
    value = result()
    timestamp, offline = value["timestamp_evidence"], value["offline_verification"]
    assert timestamp["present"] is True and timestamp["non_user_forgeable"] is True
    assert timestamp["publication_to_signed_timestamp_latency_seconds"] == 0
    assert offline["network_access"] == "NONE" and offline["interfaces"] == ["lo"]
    assert offline["result"] == "FAIL"
    assert offline["repository_identity_verified"] is False
    assert "SourceRepositoryOwnerURI" in offline["failure"]
    assert value["state"] == "CLOSED_BLOCKED"
    assert value["future_policy"]["retention_horizon_acceptable"] is False
    assert all(flag is False for flag in value["authority"].values())
