import json
from pathlib import Path

import pytest

from qntylab import breadth_v2_development_campaign as campaign


def test_manifest_reconstructs_frozen_counts():
    manifest = campaign.build_manifest(repo_root=Path("."))
    assert len(manifest["registered_execution_descriptors"]) == 1992
    assert sum(row["input_status"] == "READY" for row in manifest["registered_execution_descriptors"]) == 1496
    assert sum(row["input_status"] == "BLOCKED" for row in manifest["registered_execution_descriptors"]) == 496
    assert all("breadth_v2_evaluation_id" in row and "trial_id" in row for row in manifest["registered_execution_descriptors"] if row["input_status"] == "READY")
    assert all("breadth_v2_evaluation_id" not in row for row in manifest["registered_execution_descriptors"] if row["input_status"] == "BLOCKED")


def test_manifest_digest_is_timestamp_free():
    manifest = campaign.build_manifest(repo_root=Path("."))
    assert "timestamp" not in json.dumps(manifest, sort_keys=True).lower()
    digest = manifest["campaign_execution_manifest_sha256"]
    assert digest == campaign._sha({k: v for k, v in manifest.items() if k != "campaign_execution_manifest_sha256"})


def test_existing_unexpected_evaluation_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / "research"
    root.mkdir()
    monkeypatch.setattr(campaign, "_existing_events", lambda _root: ({}, {"unexpected"}))
    manifest = {"registered_execution_descriptors": []}
    with pytest.raises(RuntimeError, match="unexpected Breadth V2 evaluation IDs"):
        campaign.execute_campaign(manifest=manifest, bundle_dir=tmp_path / "bundles", ledger_root=root)


def test_resume_skips_matching_completed_descriptor(tmp_path, monkeypatch):
    root = tmp_path / "research"
    root.mkdir()
    item = {"input_status": "READY", "breadth_v2_evaluation_id": "eval", "trial_id": "trial",
            "evaluation_input_bundle_sha256": "bundle", "execution_unit_type": "SINGLE_ASSET",
            "execution_unit_id": "BCHUSDT", "period_id": "DEV_2022", "cost_mode": "BASELINE_EXECUTION"}
    event = {key: item[key] for key in ("breadth_v2_evaluation_id", "trial_id", "evaluation_input_bundle_sha256", "execution_unit_type", "execution_unit_id", "period_id", "cost_mode")}
    monkeypatch.setattr(campaign, "_existing_events", lambda _root: ({"eval": event}, {"eval"}))
    result = campaign.execute_campaign(manifest={"registered_execution_descriptors": [item]}, bundle_dir=tmp_path / "bundles", ledger_root=root)
    assert result["attempted"] == 1496
    assert result["completed"] == 1
    assert result["unexpected_integrity_blocked"] == 0
