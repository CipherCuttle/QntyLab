from __future__ import annotations

from datetime import UTC
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from qntylab.h003_defensive_followup_v1_origin_v2 import EXPECTED_ORIGIN_UTC, parse_utc
from qntylab.h003_defensive_followup_v1_prospective_recorder_v2 import CANDIDATE_ID, VARIANT_ID
from qntylab.h003_defensive_followup_v1_prospective_source_v2 import (
    ACTIVATION_ARTIFACT_RELATIVE_PATH,
    ACTIVATION_PROJECT_ID,
    SOURCE_IMPLEMENTATION_PATH,
    SourceBlocked,
    validate_activation_authority,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MERGE = "1827bb3e753970aed0cfbd0adc27bba121b41d5d"
ACTIVATION_MERGE = "6612ce47fbcea02cd001bf9f7ca1447313a8abd2"
SOURCE_SHA256 = "74e1906f1bb54123ff77347629d5da6bafcd400b9a979d6d5526bbc6ccf08633"
RUNTIME_RELATIVE_PATH = "experiments/research/h003_defensive_followup_v1/prospective_source_v2_runtime.json"
WORKFLOW_RELATIVE_PATH = ".github/workflows/h003-prospective-operation-v2.yml"
WORKFLOW_SHA256 = "bbf881c9daec8c2cfffa8431964d26e5389f0bf1e7fbc990d3f19d39166b7d45"
SCHEDULE = "7,22,37,52 * * * *"
PYTHON_VERSION = "3.12.14"
NUMPY_VERSION = "2.5.3"
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_ARTIFACT_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"
RELEASE_PREFIX = "h003-v2-evidence-"
EVIDENCE_FILE = "h003_prospective_v2_events.jsonl"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _load(relative: str) -> dict[str, object]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_source_qualification_merge_and_bytes_are_frozen() -> None:
    source = (ROOT / SOURCE_IMPLEMENTATION_PATH).read_bytes()
    assert sha256(source).hexdigest() == SOURCE_SHA256
    committed = subprocess.check_output(
        ["git", "show", f"{SOURCE_MERGE}:{SOURCE_IMPLEMENTATION_PATH}"], cwd=ROOT
    )
    assert committed == source
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", SOURCE_MERGE, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    merge_time = parse_utc(_git("show", "-s", "--format=%cI", SOURCE_MERGE))
    assert merge_time < parse_utc(EXPECTED_ORIGIN_UTC)


def test_activation_artifact_exactly_matches_source_authority_contract() -> None:
    artifact = _load(ACTIVATION_ARTIFACT_RELATIVE_PATH)
    assert artifact == {
        "schema_version": "1.0.0",
        "project_id": ACTIVATION_PROJECT_ID,
        "state": "ACTIVE",
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "prospective_origin_utc": EXPECTED_ORIGIN_UTC,
        "source_qualification_merge_sha": SOURCE_MERGE,
        "source_implementation_path": SOURCE_IMPLEMENTATION_PATH,
        "source_implementation_sha256": SOURCE_SHA256,
        "collection_mode": "PAPER_SHADOW_ONLY",
        "market_data_recording_authorized": True,
        "signal_recording_authorized": True,
        "scheduler_authorized": True,
        "backfill": "FORBIDDEN",
        "interim_economic_verdict_authorized": False,
        "qnty_acceptance_authorized": False,
        "qntyspot_policy_authorized": False,
        "live_execution_authorized": False,
        "capital_authority": "NONE",
        "signing_authority": "NONE",
        "submission_authority": "NONE",
    }


def test_historical_runtime_binding_freezes_schedule_toolchain_and_immutable_evidence() -> None:
    runtime = _load(RUNTIME_RELATIVE_PATH)
    historical_workflow = subprocess.check_output(
        ["git", "show", f"{ACTIVATION_MERGE}:{WORKFLOW_RELATIVE_PATH}"], cwd=ROOT
    )
    assert sha256(historical_workflow).hexdigest() == WORKFLOW_SHA256
    assert runtime == {
        "schema_version": "1.0.0",
        "project_id": "H003_PROSPECTIVE_SOURCE_V2_RUNTIME_BINDING",
        "state": "ACTIVE",
        "activation_artifact_path": ACTIVATION_ARTIFACT_RELATIVE_PATH,
        "source_qualification_merge_sha": SOURCE_MERGE,
        "source_implementation_sha256": SOURCE_SHA256,
        "workflow_path": WORKFLOW_RELATIVE_PATH,
        "workflow_sha256": WORKFLOW_SHA256,
        "schedule_utc": SCHEDULE,
        "python_version": PYTHON_VERSION,
        "numpy_version": NUMPY_VERSION,
        "checkout_action_sha": CHECKOUT_SHA,
        "setup_python_action_sha": SETUP_PYTHON_SHA,
        "upload_artifact_action_sha": UPLOAD_ARTIFACT_SHA,
        "download_artifact_action_sha": DOWNLOAD_ARTIFACT_SHA,
        "release_prefix": RELEASE_PREFIX,
        "release_asset": EVIDENCE_FILE,
        "persistence": "GITHUB_IMMUTABLE_RELEASE_HASH_CHAIN_V1",
        "immutable_release_required": True,
        "write_authority": "PERSIST_JOB_ONLY",
        "force_push": "FORBIDDEN",
        "economic_verdict": "FORBIDDEN",
        "downstream_authority": "NONE",
    }

    text = historical_workflow.decode("utf-8")
    assert f'cron: "{SCHEDULE}"' in text
    assert "cancel-in-progress: false" in text
    assert f"actions/checkout@{CHECKOUT_SHA}" in text
    assert f"actions/setup-python@{SETUP_PYTHON_SHA}" in text
    assert f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}" in text
    assert f"actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}" in text
    assert f'python-version: "{PYTHON_VERSION}"' in text
    assert f'"numpy=={NUMPY_VERSION}"' in text
    assert "persist-credentials: false" in text
    assert "GITHUB_IMMUTABLE_RELEASE_HASH_CHAIN_V1" in text
    assert "gh release create" in text
    assert "--draft" in text
    assert "gh release upload" in text
    assert "gh release edit" in text
    assert "'.immutable'" in text
    assert 'test "$TAG" = "${H003_RELEASE_PREFIX}${LAST_EVENT_DIGEST:0:24}"' in text
    assert "H003_EVIDENCE_BRANCH" not in text
    assert "git push" not in text
    assert "pull_request:" not in text

    record_section, persist_section = text.split("\n  persist:\n", 1)
    assert "  record:\n    permissions:\n      contents: read" in record_section
    assert "contents: write" not in record_section
    assert "permissions:\n      contents: write" in persist_section
    assert "actions/checkout@" not in persist_section
    assert "GH_TOKEN: ${{ github.token }}" in persist_section


def test_activation_is_not_authority_until_artifact_is_canonical_on_origin_master() -> None:
    canonical = _git(
        "log",
        "--first-parent",
        "-1",
        "--format=%H",
        "origin/master",
        "--",
        ACTIVATION_ARTIFACT_RELATIVE_PATH,
    )
    if not canonical:
        with pytest.raises(SourceBlocked, match="activation lineage is incomplete"):
            validate_activation_authority(ROOT)
        return

    authority = validate_activation_authority(ROOT)
    assert authority["operation_mode"] == "CANONICAL_PROSPECTIVE_SHADOW"
    assert authority["source_qualification_merge_sha"] == SOURCE_MERGE
    assert authority["source_implementation_sha256"] == SOURCE_SHA256
    activated_at = parse_utc(str(authority["activation_canonicalized_at_utc"]))
    assert activated_at.tzinfo == UTC
    assert activated_at < parse_utc(EXPECTED_ORIGIN_UTC)
