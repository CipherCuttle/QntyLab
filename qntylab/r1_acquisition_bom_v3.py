"""Deterministic, outcome-blind raw-acquisition BOM for frozen R1 inputs.

This module plans source retrieval only.  It does not fetch data, assign raw
observations to instances, or materialize market/funding records.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path

from qntylab.r1_input_bom import CUTOFF, FUNDING_SAFE_SEGMENT_DAYS, _segments, archive_directory_url, canonical_bytes, canonical_hash


ARTIFACT = "r1_population_raw_acquisition_bom_v3"
HISTORICAL_END = CUTOFF
FUNDING_ENDPOINT = "https://api.bybit.com/v5/market/funding/history"
FROZEN_SHA256 = {
    "sprint_v2_results_sha256": "01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d",
    "instance_domain_v2_sha256": "de4dc1adef705684d2f14c77efca74c717280fc01c71c09f01a6f317cd8380e9",
    "required_domain_v2_sha256": "bfa25624f399ff68ac33cab3681181915ea88afceb8c18fbf98d708e75ba9b07",
    "acquisition_semantics_v2_sha256": "dd640a6f45881b68896ef36ee44d059d46c00bc15dc0887cde0dd9bb12cb0663",
    "availability_v2_sha256": "18ed6492676f8cde5d3d84af995bf45b46c74068e7316ebe16ad998688385580",
}

RECEIPT_FIELDS = [
    "source_url_or_query", "retrieval_timestamp_utc", "http_or_result_state", "byte_size",
    "sha256", "parser_schema_result", "stream_id", "cache_key", "retry_count",
]


def _day_range(start: str, end: str) -> list[str]:
    cursor, last = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
    values = []
    while cursor <= last:
        values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _cache_key(stream_id: str, kind: str, identity: str) -> str:
    return sha256(f"{stream_id}|{kind}|{identity}".encode()).hexdigest()


def _stable_value(value: object) -> object:
    """Canonicalize unordered frozen input collections for semantic receipts."""
    if isinstance(value, dict):
        return {key: _stable_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        items = [_stable_value(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    return value


def _stable_hash(value: object) -> str:
    return canonical_hash(_stable_value(value))


def _funding_segments(symbol: str, start_utc: str) -> list[dict]:
    return [{
        **segment,
        "query": {
            "category": "linear", "symbol": symbol, "startTime": segment["start_utc"],
            "endTime": segment["end_utc"], "limit": 200,
        },
    } for segment in _segments(start_utc[:10], HISTORICAL_END[:10], FUNDING_SAFE_SEGMENT_DAYS)]


def build_required_acquisition(domain: dict, required_domain: dict, acquisition: dict) -> dict:
    """Build availability-independent acquisition instructions from frozen inputs."""
    instances = {row["instrument_instance_id"]: row for row in domain["instances"]}
    required = {row["instrument_instance_id"]: row for row in required_domain["records"]}
    streams = []
    for source in sorted(acquisition["streams"], key=lambda row: row["stream_id"]):
        stream_id, consumers = source["stream_id"], source["consumer_instance_ids"]
        if not consumers or any(instance_id not in required for instance_id in consumers):
            raise ValueError(f"invalid consumers for {stream_id}")
        if any(not required[instance_id]["structurally_relevant_to_r1"] for instance_id in consumers):
            raise ValueError(f"non-relevant consumer in {stream_id}")
        key = source["acquisition_stream_key"]
        if any(instances[instance_id]["symbol"] != key["symbol"] for instance_id in consumers):
            raise ValueError(f"symbol mismatch for {stream_id}")
        envelope = source["source_acquisition_envelope"]
        if envelope["end_utc"] != HISTORICAL_END or envelope["start_utc"] > HISTORICAL_END:
            raise ValueError(f"invalid historical envelope for {stream_id}")
        starts = [value for instance_id in consumers for value in (
            required[instance_id]["market"]["required_start_utc"], required[instance_id]["funding"]["required_start_utc"]
        ) if value]
        if envelope["start_utc"] != min(starts) + "T00:00:00Z":
            raise ValueError(f"acquisition start is not frozen-required minimum for {stream_id}")
        structural_intervals = []
        for instance_id in sorted(consumers):
            market = required[instance_id]["market"]
            if market["interval_state"] == "DETERMINATE":
                structural_intervals.append({
                    "instrument_instance_id": instance_id,
                    "start_utc": market["required_start_utc"] + "T00:00:00Z",
                    "end_utc": market["required_end_utc"] + "T23:59:59Z",
                    "expected_object_count": market["required_object_count"],
                    "object_url_template": market["expected_source_path_template"],
                })
        index_url = archive_directory_url(key["symbol"])
        stream_start = envelope["start_utc"]
        streams.append({
            "stream_id": stream_id,
            "venue": key["venue"], "symbol": key["symbol"], "contract_type": key["contract_type"],
            "consumer_instance_ids": sorted(consumers),
            "unassigned_consumer_instance_ids": sorted(source["unassigned_consumer_instance_ids"]),
            "source_acquisition_envelope": envelope,
            "market_acquisition_plan": {
                "archive_index_url": index_url,
                "enumeration_scope": {"start_utc": stream_start, "end_utc": HISTORICAL_END},
                "object_identity": "UTC date D with path <archive_index_url><symbol>D.csv.gz",
                "object_url_template": f"{index_url}{key['symbol']}{{utc_date}}.csv.gz",
                "availability_state_before_retrieval": "SOURCE_UNKNOWN",
                "expected_hash_state_after_retrieval": "SHA256_REQUIRED_AFTER_RETRIEVAL",
                "cache_destination_template": f"data/raw/r1/v3/{_cache_key(stream_id, 'market-index', index_url)}/market/{{utc_date}}.csv.gz",
                "deduplication_key": "stream_id + UTC source date",
                "resume_rule": "existing object is reusable only after byte SHA-256 and parser/schema receipt verify",
                "structural_required_intervals": structural_intervals,
            },
            "funding_acquisition_plan": {
                "endpoint": FUNDING_ENDPOINT,
                "envelope_start_utc": stream_start, "envelope_end_utc": HISTORICAL_END,
                "segments": _funding_segments(key["symbol"], stream_start),
                "cache_destination_template": f"data/raw/r1/v3/{_cache_key(stream_id, 'funding', stream_start)}/funding/{{start_utc}}_{{end_utc}}.json",
                "deduplication_key": "stream_id + start_utc + end_utc",
                "response_contract": "realized settlements only; preserve source timestamps and do not synthesize intervals",
                "pagination_contract": {
                    "limit": 200,
                    "initial_segment_days": FUNDING_SAFE_SEGMENT_DAYS,
                    "on_200_records": "bisect exact UTC segment until each leaf is below cap or report NON_ENUMERABLE",
                    "required_checks": ["range gaps", "duplicate timestamps", "non-monotonic timestamps", "boundary duplication", "boundary omission", "empty valid response", "HTTP/API failure"],
                },
            },
            "assignment_contract": {
                "states": ["OUTSIDE_HISTORICAL_ACQUISITION_ENVELOPE", "UNASSIGNED", "ASSIGNED_TO_INSTRUMENT_INSTANCE", "UNASSIGNED_AMBIGUOUS"],
                "normalization_gate": "only ASSIGNED_TO_INSTRUMENT_INSTANCE may enter DailyMarket or FundingSettlement normalization",
                "assignment_windows": source["assignment_windows"],
            },
        })
    return {
        "artifact": "r1_required_raw_acquisition_plan_v3", "outcome_embargo": True,
        "historical_cutoff_utc": HISTORICAL_END,
        "future_reservoir_start_utc": "2026-07-01T00:00:00Z",
        "source_stream_count": len(streams),
        "consumer_instance_count": sum(len(row["consumer_instance_ids"]) for row in streams),
        "assignment_quarantine_count": sum(len(row["unassigned_consumer_instance_ids"]) for row in streams),
        "mechanical_receipt_contract": {"required_fields": RECEIPT_FIELDS, "failure_states": ["SOURCE_PRESENT", "SOURCE_ABSENT", "SOURCE_UNKNOWN", "TRANSPORT_FAILURE", "SCHEMA_FAILURE", "HASH_MISMATCH"], "assignment_states_are_later": True},
        "streams": streams,
    }


def build_availability_annotation(required_domain: dict, availability: dict, required_plan: dict) -> dict:
    """Classify only observed v2 structural availability; never alter requirements."""
    requirements = {row["instrument_instance_id"]: row for row in required_domain["records"]}
    observed = {row["instrument_instance_id"]: row for row in availability["records"]}
    structural_absences, present, sand = [], 0, None
    for instance_id, row in sorted(requirements.items()):
        market = row["market"]
        if not row["structurally_relevant_to_r1"] or market["interval_state"] != "DETERMINATE":
            continue
        observation = observed.get(instance_id)
        if observation is None:
            raise ValueError(f"missing v2 availability observation for {instance_id}")
        dates = set(_day_range(market["required_start_utc"], market["required_end_utc"]))
        absent = sorted(observation.get("absent_dates", []))
        if any(value not in dates for value in absent):
            raise ValueError(f"availability date outside required interval for {instance_id}")
        present += market["required_object_count"] - len(absent)
        for utc_date in absent:
            item = {"instrument_instance_id": instance_id, "symbol": row["symbol"], "utc_date": utc_date, "classification": "GENUINE_STRUCTURAL_REQUIRED_DAY_ABSENCE"}
            structural_absences.append(item)
            if row["symbol"] == "SANDUSDT" and utc_date == "2024-11-04":
                sand = item
    if len(structural_absences) != availability["counts"]["absent"] or present != availability["counts"]["present"]:
        raise ValueError("v2 availability counts do not reconcile")
    return {
        "artifact": "r1_raw_acquisition_availability_annotation_v3", "outcome_embargo": True,
        "availability_scope": "v2 observations cover frozen structural required dates; raw source-index-only objects remain unobserved until a later index retrieval",
        "availability_source_semantic_sha256": _stable_hash(availability),
        "required_acquisition_sha256": canonical_hash(required_plan),
        "observed_structural_market_objects": {"present": present, "absent": len(structural_absences), "unknown": availability["counts"]["unknown"]},
        "absence_reclassification": {
            "genuine_structural_required_day_absence": structural_absences,
            "source_only_absence_outside_required_interval": {"state": "NOT_OBSERVED_BY_V2_STRUCTURAL_AVAILABILITY", "count": None},
            "enumeration_artifact": [], "other_frozen_category": [],
        },
        "sand_2024_11_04": sand,
        "availability_mutation_rule": "availability may change only this annotation; it cannot alter source streams, envelopes, funding segments, or required_acquisition_sha256",
    }


def build_bom_v3(domain: dict, required_domain: dict, acquisition: dict, availability: dict) -> dict:
    required_plan = build_required_acquisition(domain, required_domain, acquisition)
    annotation = build_availability_annotation(required_domain, availability, required_plan)
    return {
        "artifact": ARTIFACT, "verdict": "R1_FREE_INPUT_BOM_READY", "outcome_embargo": True,
        "frozen_receipts": {"instance_domain_v2_semantic_sha256": _stable_hash(domain), "required_domain_v2_semantic_sha256": _stable_hash(required_domain), "acquisition_semantics_v2_semantic_sha256": _stable_hash(acquisition), "availability_v2_semantic_sha256": _stable_hash(availability)},
        "required_acquisition_sha256": canonical_hash(required_plan), "availability_sha256": canonical_hash(annotation),
        "required_acquisition": required_plan, "availability_annotation": annotation,
    }


def write_bom_v3(root: Path) -> dict:
    data = root / "experiments/data"
    paths = {
        "sprint_v2_results_sha256": root / "experiments/results/sprint_v2_results.json",
        "instance_domain_v2_sha256": data / "r1_historical_instance_domain_v2.json",
        "required_domain_v2_sha256": data / "r1_population_input_required_domain_v2.json",
        "acquisition_semantics_v2_sha256": data / "r1_acquisition_semantics_closure_v2.json",
        "availability_v2_sha256": data / "r1_population_market_availability_v2.json",
    }
    actual = {name: sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if actual != FROZEN_SHA256:
        raise ValueError(f"frozen receipt mismatch: {actual}")
    bom = build_bom_v3(*(json.loads(paths[name].read_text()) for name in ("instance_domain_v2_sha256", "required_domain_v2_sha256", "acquisition_semantics_v2_sha256", "availability_v2_sha256")))
    bom["frozen_file_sha256"] = actual
    artifact_path = data / "r1_population_raw_acquisition_bom_v3.json"
    artifact_path.write_bytes(canonical_bytes(bom))
    report = "\n".join([
        "# R1 population input BOM v3", "", "## VERDICT", "", bom["verdict"], "", "## COUNTS", "",
        f"- Source-native streams: {bom['required_acquisition']['source_stream_count']}",
        f"- Relevant instance consumers: {bom['required_acquisition']['consumer_instance_count']}",
        f"- Assignment-quarantined consumers: {bom['required_acquisition']['assignment_quarantine_count']}",
        f"- Funding acquisition envelopes unknown: 0", f"- Structural observed present / absent / unknown: {bom['availability_annotation']['observed_structural_market_objects']['present']} / {bom['availability_annotation']['observed_structural_market_objects']['absent']} / {bom['availability_annotation']['observed_structural_market_objects']['unknown']}",
        "", "## HANDOFF", "", "The plan is source-level, cutoff-bounded, availability-independent, resumable, and assignment-gated. It neither retrieves data nor materializes instance-bound records.",
        "", "## OUTCOME EMBARGO", "", "No strategy outcomes or execution results were produced.",
    ])
    (root / "experiments/results/R1_FREE_INPUT_BOM_V3.md").write_text(report + "\n")
    return bom


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        print(json.dumps(write_bom_v3(Path.cwd()), sort_keys=True))
