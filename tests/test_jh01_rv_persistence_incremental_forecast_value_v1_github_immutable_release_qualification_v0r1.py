from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_immutable_release_persistence_backend_qualification_v0r1.json"
V0 = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_immutable_release_persistence_backend_qualification_v0.json"


def result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_frozen_preregistration_and_predecessors_are_unchanged() -> None:
    value = result()
    frozen = value["frozen_v1_authority"]
    prereg = ROOT / frozen["path"]
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == frozen["bytes_sha256"]
    assert json.loads(prereg.read_text(encoding="utf-8"))["preregistration_digest"] == frozen["preregistration_digest"]
    assert (frozen["first_origin"], frozen["last_origin"], frozen["required_origin_count"]) == ("2026-09-15T00:00:00Z", "2027-09-14T00:00:00Z", 365)
    assert json.loads(V0.read_text(encoding="utf-8"))["state"] == "CLOSED_BLOCKED"
    assert all(item["reopened"] is False for item in value["predecessors"].values())


def test_live_release_evidence_is_non_scientific_and_immutable() -> None:
    value = result()
    setting = value["repository_setting"]
    release = value["synthetic_qualification"]
    properties = value["live_property_results"]
    assert setting["before"]["enabled"] is False and setting["after"]["enabled"] is True
    assert (setting["enablement"]["http_status"], setting["readback"]) == (204, "PASS")
    assert all(release[key] is False for key in ("real_v1_forecast", "scientific_evidence", "research_result", "promotion_eligible"))
    assert properties["immutable_flag"] is True and properties["asset_identity_verified"] is True
    assert properties["asset_mutation_rejected"]["http_status"] == properties["asset_delete_rejected"]["http_status"] == 422
    assert properties["tag_move_rejected"] is True and properties["same_tag_competing_release_rejected"]["http_status"] == 422
    assert properties["latest_wins"] is False and properties["backfill"] is False


def test_sanitized_live_receipts_record_policy_mutation_and_rejections() -> None:
    value = result()
    receipts = json.loads((ROOT / value["qualification_receipts_path"]).read_text(encoding="utf-8"))
    assert receipts["repository_setting"]["before"]["response"]["enabled"] is False
    assert receipts["repository_setting"]["enablement"]["http_status"] == 204
    assert receipts["repository_setting"]["readback"]["response"]["enabled"] is True
    assert all(probe["exit_code"] == 1 for probe in receipts["bounded_rejection_probes"].values())
    assert receipts["verification"]["release"]["exit_code"] == receipts["verification"]["asset"]["exit_code"] == 0


def test_authoritative_time_and_exact_asset_identity_are_frozen() -> None:
    value = result()
    artifact = ROOT / value["synthetic_qualification"]["artifact_path"]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == value["synthetic_qualification"]["local_artifact_sha256"]
    assert value["synthetic_qualification"]["remote_asset_digest"] == "sha256:" + value["synthetic_qualification"]["local_artifact_sha256"]
    timing = value["publication_time_evidence"]
    assert timing["github_published_at"] == timing["subsequent_get_published_at"]
    assert timing["server_observed_published_at"] is True
    assert timing["caller_can_backdate_published_at"] is False
    assert timing["caller_timestamp_authority_rejected"] is True and timing["local_git_timestamp_authority_rejected"] is True


def test_retention_gap_blocks_all_follow_on_authority() -> None:
    value = result()
    retention = value["retention_and_attestation"]
    assert value["state"] == "CLOSED_BLOCKED"
    assert value["block_reason"] == "RELEASE_ATTESTATION_OFFLINE_ARCHIVAL_NOT_VERIFIABLE_WITH_CURRENT_OFFICIAL_GITHUB_CLI"
    assert retention["release_verify_live"] == "PASS"
    assert retention["authenticatable_later"] is False and retention["retention_horizon_acceptable"] is False
    assert all(flag is False for flag in value["outcome_blindness"].values())
    assert all(flag is False for flag in value["authority"].values())
