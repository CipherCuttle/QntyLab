from hashlib import sha256
import json
from pathlib import Path

from qntylab.r1_acquisition_semantics import (ASSIGNED, OUTSIDE, UNASSIGNED, UNASSIGNED_AMBIGUOUS,
                                               assigned_projection, assign_observation,
                                               build_acquisition_closure,
                                               may_enter_instance_normalization)
from qntylab.r1_input_bom import canonical_bytes, required_domain


def instance(instance_id, *, start, end_state, lifecycle, lineage):
    return {"instrument_instance_id": instance_id, "symbol": "MONUSDT", "contract_type": "LinearPerpetual",
            "lineage": lineage, "start_time": start, "start_state": "FIRST_CAUSAL_TRADABILITY_EVIDENCE",
            "end_state": end_state, "identity_state": "REUSE_EVIDENCED_BOUNDARY_UNTIMED",
            "lifecycle_state": lifecycle, "ambiguity_reasons": []}


def test_source_stream_is_shared_but_ambiguous_prior_lineage_is_quarantined():
    prior = instance("bybit|MONUSDT|linearperpetual|prior", start="2024-05-30T00:00:00Z",
                     end_state="AMBIGUOUS_TERMINAL", lifecycle="TERMINATED_AMBIGUOUS", lineage="prior")
    current = instance("bybit|MONUSDT|linearperpetual|current", start="2025-11-24T00:00:00Z",
                       end_state="OPEN_AT_HISTORICAL_CUTOFF", lifecycle="OPEN_AT_CUTOFF_CORROBORATED", lineage="current")
    domain = {"instances": [prior, current]}
    required = required_domain({"compiled_instrument_instance_count": 2, "instances": [prior, current]})
    closure = build_acquisition_closure(domain, required)
    stream = closure["streams"][0]
    assert stream["consumer_instance_ids"] == sorted([prior["instrument_instance_id"], current["instrument_instance_id"]])
    assert stream["unassigned_consumer_instance_ids"] == [prior["instrument_instance_id"]]
    assert assign_observation(stream, {"event_time": "2025-01-01T00:00:00Z"})["assignment_state"] == UNASSIGNED
    assigned = assign_observation(stream, {"event_time": "2026-01-01T00:00:00Z"})
    assert assigned["assignment_state"] == ASSIGNED and assigned["instrument_instance_id"] == current["instrument_instance_id"]


def test_later_raw_evidence_does_not_change_historical_projection():
    current = instance("bybit|MONUSDT|linearperpetual|current", start="2025-11-24T00:00:00Z",
                       end_state="OPEN_AT_HISTORICAL_CUTOFF", lifecycle="OPEN_AT_CUTOFF_CORROBORATED", lineage="current")
    domain = {"instances": [current]}
    required = required_domain({"compiled_instrument_instance_count": 1, "instances": [current]})
    stream = build_acquisition_closure(domain, required)["streams"][0]
    before_t = [{"observation_id": "before", "event_time": "2026-01-01T00:00:00Z", "availability_time": "2026-01-01T00:00:00Z", "retrieval_time": "2026-01-02T00:00:00Z"}]
    later = {"observation_id": "later", "event_time": "2026-02-01T00:00:00Z", "availability_time": "2026-02-01T00:00:00Z", "retrieval_time": "2026-02-02T00:00:00Z"}
    assert assigned_projection(stream, before_t, "2026-01-31T23:59:59Z") == assigned_projection(stream, before_t + [later], "2026-01-31T23:59:59Z")


def determinate_stream(*windows, cutoff="2026-06-30"):
    instances = [{"instrument_instance_id": instance_id, "symbol": "MONUSDT", "contract_type": "LinearPerpetual"}
                 for instance_id, _start, _end in windows]
    records = [{"instrument_instance_id": instance_id, "structurally_relevant_to_r1": True,
                "market": {"interval_state": "DETERMINATE", "required_start_utc": start, "required_end_utc": end},
                "funding": {"required_start_utc": start, "required_end_utc": end}}
               for instance_id, start, end in windows]
    stream = build_acquisition_closure({"instances": instances}, {"records": records})["streams"][0]
    stream["source_acquisition_envelope"]["end_utc"] = cutoff + "T23:59:59Z"
    return stream


def test_zero_one_multiple_assignment_states_are_distinct_and_cannot_normalize():
    zero = determinate_stream(("bybit|MONUSDT|linearperpetual|only", "2025-02-01", "2025-02-02"))
    one = determinate_stream(("bybit|MONUSDT|linearperpetual|one", "2025-01-01", "2025-12-31"))
    multiple = determinate_stream(("bybit|MONUSDT|linearperpetual|a", "2025-01-01", "2025-12-31"),
                                  ("bybit|MONUSDT|linearperpetual|b", "2025-01-01", "2025-12-31"))
    zero_assignment = assign_observation(zero, {"event_time": "2025-03-01T00:00:00Z"})
    one_assignment = assign_observation(one, {"event_time": "2025-03-01T00:00:00Z"})
    multiple_assignment = assign_observation(multiple, {"event_time": "2025-03-01T00:00:00Z"})
    assert zero_assignment["assignment_state"] == UNASSIGNED
    assert one_assignment["assignment_state"] == ASSIGNED
    assert multiple_assignment["assignment_state"] == UNASSIGNED_AMBIGUOUS
    assert not may_enter_instance_normalization(zero_assignment)
    assert may_enter_instance_normalization(one_assignment)
    assert not may_enter_instance_normalization(multiple_assignment)


def test_verified_terminal_is_not_extended_by_source_acquisition_envelope():
    stream = determinate_stream(("bybit|TERMUSDT|linearperpetual|verified", "2024-01-01", "2025-02-01"))
    assignment = assign_observation(stream, {"event_time": "2025-03-01T00:00:00Z"})
    assert assignment["assignment_state"] == UNASSIGNED
    assert assignment["candidate_instance_ids"] == []


def test_acquisition_window_cannot_widen_assignment_window():
    narrow = determinate_stream(("bybit|MONUSDT|linearperpetual|one", "2025-01-01", "2025-02-01"), cutoff="2025-03-01")
    wide = determinate_stream(("bybit|MONUSDT|linearperpetual|one", "2025-01-01", "2025-02-01"), cutoff="2026-06-30")
    shared = {"event_time": "2025-02-15T00:00:00Z"}
    assert assign_observation(narrow, shared) == assign_observation(wide, shared)
    assert assign_observation(wide, {"event_time": "2025-04-01T00:00:00Z"})["assignment_state"] == UNASSIGNED


def test_mon_lineages_do_not_merge_and_overlap_is_ambiguous():
    stream = determinate_stream(("bybit|MONUSDT|linearperpetual|prior", "2024-01-01", "2024-12-31"),
                                ("bybit|MONUSDT|linearperpetual|current", "2025-03-01", "2025-12-31"))
    assert assign_observation(stream, {"event_time": "2024-06-01T00:00:00Z"})["instrument_instance_id"].endswith("|prior")
    assert assign_observation(stream, {"event_time": "2025-06-01T00:00:00Z"})["instrument_instance_id"].endswith("|current")
    assert assign_observation(stream, {"event_time": "2025-02-01T00:00:00Z"})["assignment_state"] == UNASSIGNED
    overlap = determinate_stream(("bybit|MONUSDT|linearperpetual|a", "2025-01-01", "2025-12-31"),
                                 ("bybit|MONUSDT|linearperpetual|b", "2025-06-01", "2025-12-31"))
    assert assign_observation(overlap, {"event_time": "2025-07-01T00:00:00Z"})["assignment_state"] == UNASSIGNED_AMBIGUOUS


def test_ambiguous_terminal_quarantine_and_future_reservoir_cutoff_are_preserved():
    prior = instance("bybit|MONUSDT|linearperpetual|prior", start="2024-05-30T00:00:00Z",
                     end_state="AMBIGUOUS_TERMINAL", lifecycle="TERMINATED_AMBIGUOUS", lineage="prior")
    domain = {"instances": [prior]}
    required = required_domain({"compiled_instrument_instance_count": 1, "instances": [prior]})
    stream = build_acquisition_closure(domain, required)["streams"][0]
    assert stream["assignment_windows"] == []
    assert assign_observation(stream, {"event_time": "2025-01-01T00:00:00Z"})["assignment_state"] == UNASSIGNED
    assert assign_observation(stream, {"event_time": "2026-07-01T00:00:00Z"})["assignment_state"] == OUTSIDE


def test_v2_candidate_is_canonical_and_binds_current_regression_receipt():
    root = Path(__file__).parents[1]
    candidate_path = root / "experiments/data/r1_acquisition_semantics_closure_v2.json"
    candidate_bytes = candidate_path.read_bytes()
    candidate = json.loads(candidate_bytes)
    assert candidate_bytes == canonical_bytes(candidate)
    assert candidate["artifact"] == "r1_acquisition_semantics_closure_v2"
    assert candidate["test_receipt"]["test_module_sha256"] == sha256(Path(__file__).read_bytes()).hexdigest()
