"""Freeze raw-source acquisition separately from R1 instance materialization.

This module is deliberately outcome-blind.  It describes a source-native
evidence envelope; it neither downloads data nor changes lifecycle, PIT, or
eligibility state.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from qntylab.r1_input_bom import CUTOFF, canonical_bytes, canonical_hash


ARTIFACT = "r1_acquisition_semantics_closure_v2"
REJECTED_CANDIDATE_SHA256 = "c6dd923d18c0836c837f9815d373d07877fff89ceafc08d1c8ef7647585d5c2f"
UNASSIGNED = "UNASSIGNED"
UNASSIGNED_AMBIGUOUS = "UNASSIGNED_AMBIGUOUS"
ASSIGNED = "ASSIGNED_TO_INSTRUMENT_INSTANCE"
OUTSIDE = "OUTSIDE_HISTORICAL_ACQUISITION_ENVELOPE"

FROZEN_ANCHORS = {
    "sprint_v2_sha256": "01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d",
    "instance_domain_v2_sha256": "de4dc1adef705684d2f14c77efca74c717280fc01c71c09f01a6f317cd8380e9",
    "required_domain_v2_sha256": "bfa25624f399ff68ac33cab3681181915ea88afceb8c18fbf98d708e75ba9b07",
    "availability_v2_sha256": "18ed6492676f8cde5d3d84af995bf45b46c74068e7316ebe16ad998688385580",
}


def acquisition_stream_key(instance: dict) -> dict:
    """Return the source-native identity; never use an instance id as a key."""
    return {"venue": instance["instrument_instance_id"].split("|", 1)[0],
            "symbol": instance["symbol"], "contract_type": instance["contract_type"]}


def _key_id(key: dict) -> str:
    return "|".join((key["venue"], key["symbol"], key["contract_type"]))


def _assignable_window(instance: dict, required: dict) -> dict | None:
    """Only a frozen determinate interval can admit evidence to an instance."""
    market = required["market"]
    if (market["interval_state"] != "DETERMINATE" or
            not market["required_start_utc"] or not market["required_end_utc"]):
        return None
    return {"instrument_instance_id": instance["instrument_instance_id"],
            "start_utc": market["required_start_utc"] + "T00:00:00Z",
            "end_utc": market["required_end_utc"] + "T23:59:59Z",
            "rule": "event_time within pre-frozen determinate structural interval"}


def build_acquisition_closure(domain: dict, required_domain: dict) -> dict:
    """Build an acquisition-only stream registry from frozen v2 inputs.

    A source stream may have many consumers.  Assignment windows are a strict
    subset of its envelope, so acquisition never recreates eligibility.
    """
    instances = {row["instrument_instance_id"]: row for row in domain["instances"]}
    required = {row["instrument_instance_id"]: row for row in required_domain["records"]}
    streams: dict[str, dict] = {}
    for instance_id, row in sorted(required.items()):
        if not row["structurally_relevant_to_r1"]:
            continue
        instance = instances[instance_id]
        key = acquisition_stream_key(instance)
        key_id = _key_id(key)
        stream = streams.setdefault(key_id, {"acquisition_stream_key": key, "consumer_instance_ids": [],
                                              "source_start_candidates_utc": [], "assignment_windows": [],
                                              "unassigned_consumer_instance_ids": []})
        stream["consumer_instance_ids"].append(instance_id)
        starts = [value for value in (row["market"]["required_start_utc"], row["funding"]["required_start_utc"]) if value]
        stream["source_start_candidates_utc"].extend(starts)
        window = _assignable_window(instance, row)
        if window is None:
            stream["unassigned_consumer_instance_ids"].append(instance_id)
        else:
            stream["assignment_windows"].append(window)
    records = []
    for key_id, stream in sorted(streams.items()):
        if not stream["source_start_candidates_utc"]:
            raise ValueError(f"stream {key_id} has no frozen required start")
        windows = sorted(stream["assignment_windows"], key=lambda row: (row["start_utc"], row["instrument_instance_id"]))
        records.append({"stream_id": key_id, "acquisition_stream_key": stream["acquisition_stream_key"],
                        "consumer_instance_ids": sorted(stream["consumer_instance_ids"]),
                        "source_acquisition_envelope": {"start_utc": min(stream["source_start_candidates_utc"]) + "T00:00:00Z",
                                                        "end_utc": CUTOFF,
                                                        "rule": "retrieve source-native evidence only through the historical cutoff"},
                        "assignment_windows": windows,
                        "unassigned_consumer_instance_ids": sorted(stream["unassigned_consumer_instance_ids"]),
                        "assignment_rule": "zero windows is UNASSIGNED; exactly one pre-frozen window is ASSIGNED; multiple windows is UNASSIGNED_AMBIGUOUS"})
    return {"artifact": ARTIFACT, "outcome_embargo": True,
            "parent_rejected_candidate_sha256": REJECTED_CANDIDATE_SHA256,
            "implementation_version": "v2_zero_multiple_and_assignment_window_repair",
            "frozen_inputs": {"instance_domain_v2_sha256": canonical_hash(domain),
                              "required_domain_v2_sha256": canonical_hash(required_domain)},
            "historical_cutoff_utc": CUTOFF,
            "source_acquisition_is_not": ["InstrumentInstance assignment", "PIT eligibility", "DailyMarket materialization", "FundingSettlement materialization", "PnL generation"],
            "invariants": [
                "Raw retrieval retains source evidence but never restores lifecycle eligibility.",
                "A source-native stream key is venue, symbol, and contract_type; it is not an InstrumentInstance id.",
                "Archive absence is a structural gap only inside a pre-frozen required interval.",
                "Zero frozen assignment windows is UNASSIGNED; multiple is UNASSIGNED_AMBIGUOUS; both retain raw evidence and cannot normalize.",
                "Widening a source acquisition envelope never widens a frozen InstrumentInstance assignment window.",
                "event_time, availability_time, and retrieval_time remain distinct; retrieval alone cannot rewrite PIT state.",
                "No source evidence on or after 2026-07-01T00:00:00Z is in the historical acquisition envelope."],
            "funding_rule": "Acquire ticker-range evidence through the stream envelope; only ASSIGNED observations may be eligible for future FundingSettlement normalization. UNASSIGNED and UNASSIGNED_AMBIGUOUS cannot normalize. Never synthesize an 8-hour series.",
            "market_rule": "Enumerate or fetch exposed source objects in the stream envelope; only ASSIGNED observations may be eligible for future DailyMarket normalization. UNASSIGNED and UNASSIGNED_AMBIGUOUS cannot normalize; evaluate expected-day gaps only in frozen structural required intervals.",
            "stream_count": len(records), "streams": records}


def assign_observation(stream: dict, observation: dict) -> dict:
    """Quarantine non-unique or out-of-envelope raw observations.

    The caller must preserve the three temporal fields in ``observation``.
    This function deliberately does not produce an eligibility or market state.
    """
    event_time = observation["event_time"]
    envelope = stream["source_acquisition_envelope"]
    if not envelope["start_utc"] <= event_time <= envelope["end_utc"]:
        return {"assignment_state": OUTSIDE, "reason": "event_time_outside_frozen_stream_envelope"}
    matches = [row["instrument_instance_id"] for row in stream["assignment_windows"]
               if row["start_utc"] <= event_time <= row["end_utc"]]
    if not matches:
        return {"assignment_state": UNASSIGNED,
                "reason": "no_pre_frozen_instance_window", "candidate_instance_ids": matches}
    if len(matches) > 1:
        return {"assignment_state": UNASSIGNED_AMBIGUOUS,
                "reason": "multiple_pre_frozen_instance_windows", "candidate_instance_ids": matches}
    return {"assignment_state": ASSIGNED, "instrument_instance_id": matches[0],
            "reason": "unique_pre_frozen_instance_window"}


def may_enter_instance_normalization(assignment: dict) -> bool:
    """Only a uniquely instance-bound raw observation may enter a future normalizer."""
    return assignment["assignment_state"] == ASSIGNED


def assigned_projection(stream: dict, observations: list[dict], through_utc: str) -> list[dict]:
    """Return only assignments observable by ``through_utc``; not PIT eligibility."""
    result = []
    for observation in observations:
        if observation["event_time"] > through_utc or observation["availability_time"] > through_utc:
            continue
        result.append({"observation_id": observation["observation_id"], **assign_observation(stream, observation)})
    return result


def write_acquisition_closure(root: Path) -> dict:
    data = root / "experiments/data"
    paths = {"sprint_v2_sha256": root / "experiments/results/sprint_v2_results.json",
             "instance_domain_v2_sha256": data / "r1_historical_instance_domain_v2.json",
             "required_domain_v2_sha256": data / "r1_population_input_required_domain_v2.json",
             "availability_v2_sha256": data / "r1_population_market_availability_v2.json"}
    actual = {name: sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if actual != FROZEN_ANCHORS:
        raise ValueError(f"frozen receipt mismatch: {actual}")
    domain = json.loads(paths["instance_domain_v2_sha256"].read_text())
    required = json.loads(paths["required_domain_v2_sha256"].read_text())
    closure = build_acquisition_closure(domain, required)
    closure["frozen_receipts"] = actual
    closure["implementation_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    closure["test_receipt"] = {"test_module": "tests/test_r1_acquisition_semantics.py",
                               "test_module_sha256": sha256((root / "tests/test_r1_acquisition_semantics.py").read_bytes()).hexdigest(),
                               "required_regressions": ["zero_one_multiple_assignment_states", "verified_terminal_not_extended",
                                                        "acquisition_window_invariance", "mon_reuse", "normalization_firewall"]}
    artifact_path = data / "r1_acquisition_semantics_closure_v2.json"
    artifact_path.write_bytes(canonical_bytes(closure))
    artifact_sha256 = sha256(artifact_path.read_bytes()).hexdigest()
    report = "\n".join(["# R1 acquisition-semantics closure v2", "", "## VERDICT", "",
                          "R1_ACQUISITION_SEMANTICS_REPAIRED_PENDING_REVIEW", "", "## PROVENANCE", "",
                          f"- Rejected v1 candidate SHA-256: {REJECTED_CANDIDATE_SHA256}",
                          f"- v2 candidate SHA-256: {artifact_sha256}", "", "## ACQUISITION VS ASSIGNMENT", "",
                          "Raw source acquisition is keyed by `(venue, symbol, contract_type)` and may retain evidence through the historical cutoff.",
                          "It is not instance assignment, PIT eligibility, DailyMarket/FundingSettlement materialization, or PnL.",
                          "", "## FAIL-CLOSED ASSIGNMENT", "",
                          "Only a unique, pre-frozen determinate assignment window may admit an observation to an InstrumentInstance.",
                          "Zero windows is `UNASSIGNED`; multiple windows is `UNASSIGNED_AMBIGUOUS`. Both retain raw evidence but cannot normalize.",
                          "A source envelope may be wider than an instance window and never widens that window.",
                          "", "## COUNTS", "", f"- Source-native streams: {closure['stream_count']}",
                          f"- Historical cutoff: {CUTOFF}", "", "## OUTCOME EMBARGO", "",
                          "No census, raw download, R1 execution, factor calculation, rank, return, PnL, or statistical result was produced."])
    (root / "experiments/results/R1_ACQUISITION_SEMANTICS_CLOSURE_V2.md").write_text(report + "\n")
    return closure


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        print(json.dumps(write_acquisition_closure(Path.cwd()), sort_keys=True))
