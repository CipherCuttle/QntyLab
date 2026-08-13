from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_immutable_release_persistence_backend_qualification_v0.json"


def result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_disabled_immutable_release_setting_blocks_before_any_release_write() -> None:
    value = result()
    setting = value["repository_setting_check"]
    execution = value["qualification_execution"]
    assert value["state"] == "CLOSED_BLOCKED"
    assert value["block_reason"] == "BLOCKED_NEEDS_IMMUTABLE_RELEASE_ENABLEMENT"
    assert (setting["http_status"], setting["response"], setting["immutable_releases_enabled"]) == (200, {"enabled": False, "enforced_by_owner": False}, False)
    assert setting["repository_policy_changed"] is False
    assert all(execution[key] is False for key in ("synthetic_artifact_created", "release_created"))
    assert execution["qualification_tag"] is None and execution["qualification_release_id"] is None


def test_frozen_v1_identity_and_non_scientific_boundaries_are_preserved() -> None:
    value = result()
    frozen = value["frozen_v1_authority"]
    prereg = ROOT / frozen["path"]
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == frozen["bytes_sha256"]
    assert json.loads(prereg.read_text(encoding="utf-8"))["preregistration_digest"] == frozen["preregistration_digest"]
    assert (frozen["first_origin"], frozen["last_origin"], frozen["required_origin_count"]) == ("2026-09-15T00:00:00Z", "2027-09-14T00:00:00Z", 365)
    assert all(flag is False for flag in value["outcome_blindness"].values())
    assert all(flag is False for flag in value["authority"].values())


def test_no_unproven_property_is_promoted_to_pass() -> None:
    properties = result()["property_results"]
    assert properties["IMMUTABLE_RELEASES_ENABLED"] == "NO"
    assert all(value != "YES" for value in properties.values())
    assert result()["predecessor"]["reopened"] is False
