"""Candidate-only global raw-market retention scope for frozen R1 streams.

This is a source-object retention specification, not an acquisition executor
or a scientific-domain amendment.  It intentionally consumes only the
frozen source-native stream identity and never instance/lifecycle fields.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from typing import Iterable

from qntylab.r1_input_bom import CUTOFF, canonical_hash


ARTIFACT = "r1_global_raw_retention_scope_candidate_v1"
STATUS = "CANDIDATE_NOT_YET_FROZEN"
RAW_START = "2021-07-03T00:00:00Z"
RAW_END = CUTOFF
FUTURE_RESERVOIR_START = "2026-07-01T00:00:00Z"

# These are existing raw-acquisition receipt/failure vocabulary, not lifecycle
# classifications.  Container corruption retains SOURCE_PRESENT and is
# quarantined under the existing ANOMALY_CONTAINER vocabulary.
RAW_SOURCE_DISPOSITIONS = {
    "retrieved_valid": {"source_result_state": "SOURCE_PRESENT", "raw_retention_state": "RAW_RETAINED"},
    "positive_not_found": {"source_result_state": "SOURCE_ABSENT", "raw_retention_state": "RAW_UNAVAILABLE_SOURCE_ABSENT"},
    "absence_cause_unestablished": {"source_result_state": "SOURCE_UNKNOWN", "raw_retention_state": None},
    "transport_failure": {"source_result_state": "TRANSPORT_FAILURE", "raw_retention_state": None},
    "container_or_integrity_failure": {
        "source_result_state": "SOURCE_PRESENT",
        "raw_retention_state": "RAW_QUARANTINED_ANOMALY",
        "anomaly": "ANOMALY_CONTAINER",
        "receipt_failure_states": ["SCHEMA_FAILURE", "HASH_MISMATCH"],
    },
}


def raw_source_disposition(case: str) -> dict:
    """Return a raw-only receipt disposition; it has no scientific side effect."""
    try:
        return deepcopy(RAW_SOURCE_DISPOSITIONS[case])
    except KeyError as exc:
        raise ValueError(f"unknown raw source disposition: {case}") from exc


def _day_range(start_utc: str, end_utc: str) -> Iterable[str]:
    cursor, last = date.fromisoformat(start_utc[:10]), date.fromisoformat(end_utc[:10])
    while cursor <= last:
        yield cursor.isoformat()
        cursor += timedelta(days=1)


def _stream_ids(acquisition: dict) -> list[str]:
    ids = sorted(row["stream_id"] for row in acquisition["streams"])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate frozen source-native stream id")
    return ids


def iter_market_object_ids(candidate: dict) -> Iterable[dict]:
    """Enumerate retention object identities only; never fetch or normalize."""
    scope = candidate["raw_market_retention_scope"]
    if scope["end_utc"] >= FUTURE_RESERVOIR_START:
        raise ValueError("future-reservoir dates are forbidden")
    for stream_id in candidate["frozen_stream_binding"]["stream_ids"]:
        for utc_date in _day_range(scope["start_utc"], scope["end_utc"]):
            yield {"stream_id": stream_id, "utc_date": utc_date}


def build_candidate(acquisition: dict, *, parent_head: str) -> dict:
    """Derive a candidate scope without reading consumer or lifecycle state."""
    stream_ids = _stream_ids(acquisition)
    days_per_stream = sum(1 for _ in _day_range(RAW_START, RAW_END))
    return {
        "artifact": ARTIFACT,
        "status": STATUS,
        "parent_head": parent_head,
        "outcome_embargo": True,
        "formal_qnty_firewall": "QNTY formal protocol is not an authority or mutation target for this candidate",
        "authoritative_artifacts": {
            "raw_scope_owner": "r1_acquisition_semantics_closure_v2",
            "derived_plan_owner": "r1_acquisition_bom_v3.py",
            "frozen_source_acquisition_semantics_sha256": canonical_hash(acquisition),
        },
        "frozen_stream_binding": {
            "identity": "(venue, symbol, contract_type)",
            "stream_count": len(stream_ids),
            "stream_ids": stream_ids,
            "stream_ids_sha256": sha256("\n".join(stream_ids).encode()).hexdigest(),
        },
        "raw_market_retention_scope": {
            "start_utc": RAW_START,
            "end_utc": RAW_END,
            "days_per_stream": days_per_stream,
            "expected_daily_object_count": len(stream_ids) * days_per_stream,
            "object_identity": "stream_id + UTC date",
            "rule": "enumerate raw source-object identities only; do not infer source or instrument existence",
        },
        "raw_source_dispositions": RAW_SOURCE_DISPOSITIONS,
        "firewall_invariants": [
            "RAW_RETAINED != STRUCTURALLY_REQUIRED != ASSIGNED != NORMALIZED != PIT_ELIGIBLE != STRATEGY_INPUT",
            "Raw retention does not mutate InstrumentInstance population, start_time, terminal/lifecycle state, assignment windows, or structural_required_intervals.",
            "SOURCE_ABSENT, SOURCE_UNKNOWN, HTTP status, raw presence, and raw absence are not lifecycle or scientific-admission evidence.",
            "Only the pre-existing assignment gate may admit a raw observation to a later normalizer.",
            "No source object dated on or after 2026-07-01T00:00:00Z is enumerable.",
        ],
        "scientific_outputs": [],
        "acquired_raw_corpus_sha256": None,
        "acquisition_performed": False,
        "self_freeze_authorized": False,
    }
