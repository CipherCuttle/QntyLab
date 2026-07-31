import copy
import json
from pathlib import Path
import subprocess

import pytest

from qntylab.r1_global_raw_retention_candidate import (
    ARTIFACT, FUTURE_RESERVOIR_START, RAW_END, RAW_SOURCE_DISPOSITIONS,
    RAW_START, STATUS, build_candidate, iter_market_object_ids, raw_source_disposition,
)
from qntylab.r1_input_bom import canonical_hash


ROOT = Path(__file__).parents[1]
PARENT = "512ae940afa9b7a62d12ad43f8059944e43fc227"


def frozen_acquisition():
    return json.loads((ROOT / "experiments/data/r1_acquisition_semantics_closure_v2.json").read_text())


def test_global_scope_binds_all_frozen_streams_and_exact_object_count():
    candidate = build_candidate(frozen_acquisition(), parent_head=PARENT)
    assert candidate["artifact"] == ARTIFACT
    assert candidate["status"] == STATUS
    assert candidate["frozen_stream_binding"]["stream_count"] == 894
    assert len(candidate["frozen_stream_binding"]["stream_ids"]) == 894
    scope = candidate["raw_market_retention_scope"]
    assert scope["start_utc"] == RAW_START
    assert scope["end_utc"] == RAW_END
    assert scope["days_per_stream"] == 1824
    assert scope["expected_daily_object_count"] == 1_630_656
    assert sum(1 for _ in iter_market_object_ids(candidate)) == 1_630_656


def test_lifecycle_assignment_and_consumer_start_changes_cannot_change_membership():
    original = frozen_acquisition()
    changed_later = copy.deepcopy(original)
    changed_earlier = copy.deepcopy(original)
    for stream in changed_later["streams"]:
        stream["source_acquisition_envelope"]["start_utc"] = "2026-06-30T00:00:00Z"
        stream["assignment_windows"] = []
        stream["unassigned_consumer_instance_ids"] = list(stream["consumer_instance_ids"])
    for stream in changed_earlier["streams"]:
        stream["source_acquisition_envelope"]["start_utc"] = "2021-07-03T00:00:00Z"
        stream["assignment_windows"] = list(reversed(stream["assignment_windows"]))
    baseline = build_candidate(original, parent_head=PARENT)
    for changed in (changed_later, changed_earlier):
        mutated = build_candidate(changed, parent_head=PARENT)
        assert baseline["frozen_stream_binding"] == mutated["frozen_stream_binding"]
        assert baseline["raw_market_retention_scope"] == mutated["raw_market_retention_scope"]


def test_candidate_has_no_scientific_transition_surface_or_future_enumeration():
    candidate = build_candidate(frozen_acquisition(), parent_head=PARENT)
    text = json.dumps(candidate, sort_keys=True)
    assert candidate["scientific_outputs"] == []
    assert candidate["acquired_raw_corpus_sha256"] is None
    assert candidate["acquisition_performed"] is False
    assert "DailyMarketEvidenceV1" not in text
    assert "PIT_ELIGIBLE" in text
    future = copy.deepcopy(candidate)
    future["raw_market_retention_scope"]["end_utc"] = FUTURE_RESERVOIR_START
    with pytest.raises(ValueError, match="future-reservoir"):
        next(iter_market_object_ids(future))


def test_existing_source_dispositions_are_total_and_non_lifecycle():
    assert RAW_SOURCE_DISPOSITIONS == {
        "retrieved_valid": {"source_result_state": "SOURCE_PRESENT", "raw_retention_state": "RAW_RETAINED"},
        "positive_not_found": {"source_result_state": "SOURCE_ABSENT", "raw_retention_state": "RAW_UNAVAILABLE_SOURCE_ABSENT"},
        "absence_cause_unestablished": {"source_result_state": "SOURCE_UNKNOWN", "raw_retention_state": None},
        "transport_failure": {"source_result_state": "TRANSPORT_FAILURE", "raw_retention_state": None},
        "container_or_integrity_failure": {"source_result_state": "SOURCE_PRESENT", "raw_retention_state": "RAW_QUARANTINED_ANOMALY", "anomaly": "ANOMALY_CONTAINER", "receipt_failure_states": ["SCHEMA_FAILURE", "HASH_MISMATCH"]},
    }
    serialized = json.dumps(RAW_SOURCE_DISPOSITIONS)
    assert "launch" not in serialized.lower()
    assert "lifecycle" not in serialized.lower()
    candidate = build_candidate(frozen_acquisition(), parent_head=PARENT)
    before = copy.deepcopy(candidate)
    disposition = raw_source_disposition("positive_not_found")
    assert disposition == RAW_SOURCE_DISPOSITIONS["positive_not_found"]
    assert candidate == before
    assert set(disposition) <= {"source_result_state", "raw_retention_state", "anomaly", "receipt_failure_states"}


def test_additive_candidate_receipt_binds_the_generated_spec_without_claiming_corpus_bytes():
    receipt = json.loads((ROOT / "experiments/data/r1_global_raw_retention_scope_candidate_v1.json").read_text())
    candidate = build_candidate(frozen_acquisition(), parent_head=PARENT)
    assert receipt["status"] == "FROZEN"
    assert receipt["candidate_specification_sha256"] == canonical_hash(candidate)
    assert receipt["stream_binding"] == {
        "identity": "(venue, symbol, contract_type)",
        "stream_count": 894,
        "stream_ids_sha256": candidate["frozen_stream_binding"]["stream_ids_sha256"],
    }
    assert receipt["raw_market_retention_scope"] == {
        key: candidate["raw_market_retention_scope"][key]
        for key in ("start_utc", "end_utc", "days_per_stream", "expected_daily_object_count", "object_identity")
    }
    assert receipt["acquisition_performed"] is False
    assert receipt["acquired_raw_corpus_sha256"] is None
    assert receipt["self_freeze_authorized"] is False


def test_freeze_is_governance_only_and_binds_the_retrospective_external_review():
    receipt = json.loads((ROOT / "experiments/data/r1_global_raw_retention_scope_candidate_v1.json").read_text())
    review = json.loads((ROOT / "experiments/data/r1_global_raw_retention_scope_review_v1.json").read_text())
    original = json.loads(subprocess.check_output(
        ["git", "show", "c023713180e3afcf8e2e668539208db923ab67b7:experiments/data/r1_global_raw_retention_scope_candidate_v1.json"],
        cwd=ROOT,
        text=True,
    ))
    frozen_semantics = dict(receipt)
    original_semantics = dict(original)
    for payload in (frozen_semantics, original_semantics):
        payload.pop("status", None)
        payload.pop("freeze_provenance", None)
    assert frozen_semantics == original_semantics
    assert receipt["freeze_provenance"] == {
        "candidate_commit_reviewed_sha": "c023713180e3afcf8e2e668539208db923ab67b7",
        "frozen_candidate_specification_sha256": receipt["candidate_specification_sha256"],
        "frozen_source_acquisition_semantics_sha256": receipt["authoritative_artifacts"]["frozen_source_acquisition_semantics_sha256"],
        "operator_authorization": "explicit operator authorization supplied for this governance-only freeze of the exact externally reviewed candidate; no semantic changes authorized",
        "review_receipt": "r1_global_raw_retention_scope_review_v1.json",
        "review_receipt_payload_sha256": review["review_payload_sha256"],
        "review_receipt_repository_native_at_review_time": False,
    }
    review_payload = dict(review)
    review_payload.pop("review_payload_sha256")
    assert review["review_payload_sha256"] == canonical_hash(review_payload)
    assert review["reviewed_candidate_sha"] == receipt["freeze_provenance"]["candidate_commit_reviewed_sha"]
    assert review["review_type"] == "hostile/read-only"
    assert review["changeset"] == "NONE"
    assert review["verdict"] == "PASS_SAFE_TO_FREEZE"
    assert review["origin"] == "external session transcript supplied by operator"
    assert review["repository_native_at_review_time"] is False
    assert review["persisted_retrospectively"] is True
