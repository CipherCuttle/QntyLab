"""Bounded, outcome-blind JFP03 V0R1 supplemental input materialization."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests

ROOT_REL = Path("experiments/research/jigsaw_fast_prospective_signal_discovery_v0")
OUT_REL = ROOT_REL / "materialization"
CACHE_REL = Path("data/archive/binance_jfp_v0")
PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_INPUT_MATERIALIZATION"
DESIGN_DIGEST = "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736"
EXPECTED_SCHEMA = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


class MaterializationError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest_without(value: dict[str, Any], field: str) -> str:
    return digest({key: item for key, item in value.items() if key != field})


def _month_bounds(period: str) -> tuple[int, int, int]:
    year, month = (int(part) for part in period.split("-"))
    first = datetime(year, month, 1, tzinfo=UTC)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return int(first.timestamp() * 1000), int((next_month - timedelta(hours=1)).timestamp() * 1000), int((next_month - first).total_seconds() // 3600)


def _structural_identity(payload: bytes, period: str) -> dict[str, Any]:
    first_expected, last_expected, expected_count = _month_bounds(period)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if len(names) != 1:
                raise MaterializationError("ARCHIVE_MEMBER_COUNT_INVALID")
            member = names[0]
            with archive.open(member) as raw:
                rows = list(csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline="")))
    except (zipfile.BadZipFile, OSError, UnicodeError, csv.Error) as exc:
        raise MaterializationError(f"ARCHIVE_INVALID:{type(exc).__name__}") from exc
    if not rows:
        raise MaterializationError("SCHEMA_INVALID:EMPTY_ARCHIVE")
    header = [item.strip() for item in rows[0]]
    if len(header) == 12 and header[0].lstrip("-").isdigit():
        rows.insert(0, EXPECTED_SCHEMA)
        header = EXPECTED_SCHEMA
    if header != EXPECTED_SCHEMA:
        raise MaterializationError("SCHEMA_INVALID:UNEXPECTED_KLINE_SCHEMA")
    stamps: list[int] = []
    for row in rows[1:]:
        if len(row) != 12:
            raise MaterializationError("ROW_STRUCTURE_INVALID")
        try:
            stamp = int(row[0])
            close_stamp = int(row[6])
        except ValueError as exc:
            raise MaterializationError("TIMESTAMP_STRUCTURE_INVALID") from exc
        if close_stamp != stamp + 3_599_999:
            raise MaterializationError("HOURLY_CLOSE_SEMANTICS_INVALID")
        stamps.append(stamp)
    if len(stamps) != expected_count or not stamps:
        raise MaterializationError("STRUCTURAL_COVERAGE_COUNT_INVALID")
    if stamps[0] != first_expected or stamps[-1] != last_expected:
        raise MaterializationError("STRUCTURAL_COVERAGE_ENDPOINT_INVALID")
    expected = list(range(first_expected, last_expected + 3_600_000, 3_600_000))
    if stamps != expected:
        raise MaterializationError("DUPLICATES_OR_GAPS_PRESENT")
    return {
        "archive_member_names": names,
        "schema_identity": EXPECTED_SCHEMA,
        "timestamp_unit": "milliseconds_since_epoch",
        "hourly_timestamp_semantics": "open_time UTC hour start; close_time open_time + 3599999ms",
        "raw_first_timestamp": stamps[0],
        "raw_last_timestamp": stamps[-1],
        "row_count": len(stamps),
        "duplicate_identity_count": len(stamps) - len(set(stamps)),
        "gap_integrity_disposition": "PASS",
    }


def _checksum(text: str) -> str | None:
    for token in text.split():
        if len(token) == 64:
            try:
                int(token, 16)
                return token.lower()
            except ValueError:
                pass
    return None


def _acquire(item: dict[str, Any], root: Path, get: Callable[..., Any]) -> dict[str, Any]:
    response = get(item["canonical_url"], timeout=(10, 120))
    if response.status_code != 200:
        return {**item, "status": "SOURCE_OBJECT_NOT_PUBLISHED", "http_status": response.status_code, "structural_status": "BLOCKED"}
    payload = response.content
    local = hashlib.sha256(payload).hexdigest()
    checksum_response = get(item["checksum_sidecar_identity"], timeout=(10, 30))
    official = _checksum(checksum_response.text) if checksum_response.status_code == 200 else None
    if official is None or official != local:
        return {**item, "status": "CHECKSUM_VERIFICATION_FAILED", "official_checksum": official, "local_sha256": local, "structural_status": "BLOCKED"}
    try:
        structural = _structural_identity(payload, item["calendar_period"])
    except MaterializationError as exc:
        return {**item, "status": "STRUCTURAL_VALIDATION_FAILED", "official_checksum": official, "local_sha256": local, "structural_status": "BLOCKED", "structural_failure": str(exc)}
    cache = root / CACHE_REL / f"{local}.zip"
    if not cache.exists():
        cache.write_bytes(payload)
    return {
        **item,
        "status": "MATERIALIZED_VERIFIED",
        "official_checksum_algorithm": "SHA256",
        "official_checksum": official,
        "local_sha256": local,
        "byte_size": len(payload),
        "cache_path": str(CACHE_REL / cache.name),
        **structural,
    }


def run(root: Path, get: Callable[..., Any] | None = None) -> dict[str, Any]:
    out = root / OUT_REL
    census = load_json(out / "v0r1_supplemental_source_census.json")
    authorization = load_json(out / "v0r1_input_materialization_authorization.json")
    original_manifest = load_json(out / "per_source_manifest.json")
    if census["census_digest"] != digest_without(census, "census_digest"):
        raise MaterializationError("SUPPLEMENTAL_CENSUS_DIGEST_MISMATCH")
    if authorization["authorization_digest"] != digest_without(authorization, "authorization_digest"):
        raise MaterializationError("AUTHORIZATION_DIGEST_MISMATCH")
    if authorization["bound_design_digest"] != DESIGN_DIGEST:
        raise MaterializationError("DESIGN_BINDING_MISMATCH")
    existing = [row for row in original_manifest["source_objects"] if row.get("candidate_id") == "JFP03"]
    if len(existing) != 60 or any(row.get("status") != "MATERIALIZED_VERIFIED" for row in existing):
        raise MaterializationError("ORIGINAL_60_NOT_AUTHENTICATED")
    if len({row["calendar_period"] for row in existing}) != 60:
        raise MaterializationError("ORIGINAL_60_IDENTITY_DUPLICATE")
    supplemental = census["object_classifications"]["new_supplemental_objects"]
    if [row["calendar_period"] for row in supplemental] != ["2019-12", "2025-01"]:
        raise MaterializationError("SUPPLEMENTAL_SCOPE_MISMATCH")
    auth_path = out / "v0r1_materialization_receipt.json"
    if auth_path.exists():
        raise MaterializationError("V0R1_MATERIALIZATION_ALREADY_CLOSED")
    getter = get or requests.Session().get
    acquired = [_acquire(item, root, getter) for item in supplemental]
    identities = [
        {"calendar_period": row["calendar_period"], "canonical_url": row["canonical_url"], "local_sha256": row.get("local_sha256"), "official_checksum": row.get("official_checksum"), "archive_member_names": row.get("archive_member_names"), "status": row["status"]}
        for row in existing + acquired
    ]
    qualification_body = {
        "artifact_type": "JFP03_V0R1_INPUT_QUALIFICATION",
        "project_id": PROJECT_ID,
        "design_digest": DESIGN_DIGEST,
        "original_snapshot_id": authorization["bound_original_snapshot_id"],
        "original_snapshot_digest": authorization["bound_original_snapshot_digest"],
        "supplemental_census_digest": census["census_digest"],
        "supplemental_object_count": len(acquired),
        "supplemental_authenticated_count": sum(row["status"] == "MATERIALIZED_VERIFIED" for row in acquired),
        "reused_object_count": len(existing),
        "reacquired_existing_object_count": 0,
        "composed_object_count": len(identities),
        "required_support_interval": census["required_support_interval"],
        "structural_status": "PASS" if all(row["status"] == "MATERIALIZED_VERIFIED" for row in acquired) else "BLOCKED",
        "input_disposition": "READY" if all(row["status"] == "MATERIALIZED_VERIFIED" for row in acquired) else "BLOCKED",
        "implementation_authorized": False,
        "historical_execution_authorized": False,
        "input_materialization_authorized": False,
        "scientific_features_computed": False,
        "scientific_outcomes_computed": False,
        "regression_executed": False,
        "p_values_computed": False,
    }
    qualification = {**qualification_body, "qualification_digest": digest(qualification_body)}
    snapshot_body = {
        "snapshot_version": "JFP03_V0R1",
        "project_id": PROJECT_ID,
        "original_preregistration_digest": census["frozen_bindings"]["preregistration_digest"],
        "original_candidate_census_digest": census["frozen_bindings"]["candidate_census_digest"],
        "v0r1_design_digest": DESIGN_DIGEST,
        "prior_snapshot_id": authorization["bound_original_snapshot_id"],
        "prior_snapshot_digest": authorization["bound_original_snapshot_digest"],
        "supplemental_census_digest": census["census_digest"],
        "supplemental_authorization_digest": authorization["authorization_digest"],
        "ordered_authenticated_object_identities": identities,
        "qualification_digest": qualification["qualification_digest"],
    }
    snapshot_digest = digest(snapshot_body)
    snapshot = {"artifact_type": "JFP03_V0R1_IMMUTABLE_INPUT_SNAPSHOT", "snapshot_id": f"jfp-input-v0r1-{snapshot_digest}", "snapshot_digest": snapshot_digest, "identity_semantics": snapshot_body}
    receipt_body = {
        "artifact_type": "JFP03_V0R1_INPUT_MATERIALIZATION_RECEIPT",
        "project_id": PROJECT_ID,
        "authorization_digest": authorization["authorization_digest"],
        "new_objects_authenticated": sum(row["status"] == "MATERIALIZED_VERIFIED" for row in acquired),
        "existing_objects_reused": len(existing),
        "existing_objects_reacquired": 0,
        "composed_object_count": len(identities),
        "supplemental_objects": acquired,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot_digest,
        "qualification_digest": qualification["qualification_digest"],
        "scientific_computation_performed": False,
        "historical_execution_authorized": False,
    }
    receipt = {**receipt_body, "receipt_digest": digest(receipt_body)}
    (out / "v0r1_supplemental_manifest.json").write_bytes(canonical({"supplemental_objects": acquired}) + b"\n")
    (out / "v0r1_input_qualification.json").write_bytes(canonical(qualification) + b"\n")
    (out / "v0r1_snapshot_manifest.json").write_bytes(canonical(snapshot) + b"\n")
    (out / "v0r1_materialization_receipt.json").write_bytes(canonical(receipt) + b"\n")
    return {"qualification": qualification, "snapshot": snapshot, "receipt": receipt}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve()), sort_keys=True))
