"""Outcome-blind, first-party input materialization for frozen JFP V0.

This module authenticates Binance archive bytes and validates only raw schema,
timestamps, coverage, and integrity.  It deliberately contains no feature,
outcome, or statistical computation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

PHASE_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_INPUT_MATERIALIZATION_V0"
ROOT_REL = Path("experiments/research/jigsaw_fast_prospective_signal_discovery_v0")
OUT_REL = ROOT_REL / "materialization"
CACHE_REL = Path("data/archive/binance_jfp_v0")
PREREG_DIGEST = "9e9236b34b131c13cebfb0b8043ef59043b2928fa6fcd88dd7b10909d9e8ccfe"
CENSUS_DIGEST = "d718dc1c60ceccdbd7a836a1e07b911a51511456289c09d7ff9b8c6af452df94"
CANDIDATES = ("JFP01", "JFP02", "JFP03")


class MaterializationError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / ROOT_REL / name).read_text())


def frozen_contract(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    prereg, census = _load(root, "preregistration.json"), _load(root, "candidate_census.json")
    if digest({k: v for k, v in prereg.items() if k != "preregistration_digest"}) != PREREG_DIGEST:
        raise MaterializationError("GLOBAL_BLOCK: frozen preregistration digest mismatch")
    if digest({k: v for k, v in census.items() if k != "candidate_census_digest"}) != CENSUS_DIGEST:
        raise MaterializationError("GLOBAL_BLOCK: frozen candidate census digest mismatch")
    if [c["candidate_id"] for c in census["candidates"]] != list(CANDIDATES):
        raise MaterializationError("GLOBAL_BLOCK: frozen candidate order mismatch")
    return prereg, census


def months(first: datetime, last: datetime) -> list[tuple[int, int]]:
    out = []
    cursor = first.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cursor <= last:
        out.append((cursor.year, cursor.month))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _schedule(first: datetime, last: datetime, step: timedelta) -> list[int]:
    values, cur = [], first
    while cur <= last:
        values.append(int(cur.timestamp() * 1000))
        cur += step
    return values


def _urls(family: str, year: int, month: int) -> tuple[str, str]:
    suffix = f"{year:04d}-{month:02d}"
    base = "https://data.binance.vision/data/futures/um/monthly"
    if family == "premium":
        path, name = "premiumIndexKlines/BTCUSDT/1h", f"BTCUSDT-1h-{suffix}.zip"
    elif family == "kline1h":
        path, name = "klines/BTCUSDT/1h", f"BTCUSDT-1h-{suffix}.zip"
    elif family == "aggTrades":
        path, name = "aggTrades/BTCUSDT", f"BTCUSDT-aggTrades-{suffix}.zip"
    else:
        path, name = "klines/BTCUSDT/1m", f"BTCUSDT-1m-{suffix}.zip"
    url = f"{base}/{path}/{name}"
    return url, url + ".CHECKSUM"


def source_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for year, month in months(_dt("2024-11-01T00:00:00Z"), _dt("2026-08-01T07:46:00Z")):
        for family, purpose in (("aggTrades", "FEATURE_RAW_INPUT"), ("kline1m", "TARGET_RAW_INPUT")):
            url, checksum = _urls(family, year, month)
            plan.append({"candidate_id": "JFP01", "source_family": family, "symbol": "BTCUSDT", "calendar_period": f"{year:04d}-{month:02d}", "canonical_url": url, "checksum_url": checksum, "purpose": purpose, "required_coverage": "2024-11-01T00:00:00Z..2026-08-01T07:46:00Z"})
    for candidate, family, purpose in (("JFP02", "premium", "BOTH_RAW_INPUT"), ("JFP03", "kline1h", "BOTH_RAW_INPUT")):
        for year, month in months(_dt("2020-01-01T00:00:00Z"), _dt("2024-12-31T23:00:00Z")):
            url, checksum = _urls(family, year, month)
            plan.append({"candidate_id": candidate, "source_family": family, "symbol": "BTCUSDT", "interval": "1h", "calendar_period": f"{year:04d}-{month:02d}", "canonical_url": url, "checksum_url": checksum, "purpose": purpose, "required_coverage": "2020-01-01T00:00:00Z..2024-12-31T23:00:00Z"})
    return plan


def materialization_request(root: Path) -> dict[str, Any]:
    frozen_contract(root)
    body = {"artifact_type": "JFP_FAST_INPUT_MATERIALIZATION_REQUEST_V0", "phase_id": PHASE_ID, "frozen_preregistration_digest": PREREG_DIGEST, "frozen_candidate_census_digest": CENSUS_DIGEST, "ordered_candidate_ids": list(CANDIDATES), "source_objects": source_plan(), "scientific_computation_authorized": False, "input_reacquisition_authorized_after_closure": False}
    return {**body, "request_digest": digest(body)}


def _checksum(text: str) -> str | None:
    fields = text.strip().split()
    return next((x.lower() for x in fields if len(x) == 64 and all(c in "0123456789abcdefABCDEF" for c in x)), None)


def _raw_check(family: str, payload: bytes, expected_first: int, expected_last: int) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        names = archive.namelist()
        if len(names) != 1:
            raise MaterializationError("ARCHIVE_MEMBER_COUNT_INVALID")
        rows = list(csv.reader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8", newline="")))
    except (zipfile.BadZipFile, OSError, UnicodeError, csv.Error) as exc:
        raise MaterializationError(f"ARCHIVE_INVALID:{type(exc).__name__}") from exc
    if not rows:
        raise MaterializationError("SCHEMA_INVALID:empty archive")
    header = [x.strip() for x in rows[0]]
    # Binance's older monthly files are headerless but use the same frozen
    # 12-column kline layout.  Assigning the source-declared positional schema
    # is structural admission, not a scientific transformation.
    if header and len(header) == 12 and header[0].lstrip("-").isdigit():
        rows.insert(0, ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"])
        header = rows[0]
    required = {"open_time", "close", "quote_volume", "taker_buy_quote_volume"} if family in ("premium", "kline1h") else {"id", "price", "qty", "time", "is_buyer_maker"}
    if not required <= set(header):
        raise MaterializationError("SCHEMA_INVALID:required columns missing")
    index = {name: header.index(name) for name in required}
    stamps = [int(row[index["open_time"] if "open_time" in index else "time"]) for row in rows[1:] if len(row) == len(header)]
    if not stamps or stamps[0] != expected_first or stamps[-1] != expected_last:
        raise MaterializationError("RAW_COVERAGE_ENDPOINT_MISMATCH")
    if len(stamps) != len(set(stamps)) or stamps != sorted(stamps):
        raise MaterializationError("DUPLICATE_OR_NONMONOTONIC_TIMESTAMP")
    if family in ("premium", "kline1h"):
        for row in rows[1:]:
            if not all(math.isfinite(float(row[index[k]])) for k in ("close", "quote_volume", "taker_buy_quote_volume")):
                raise MaterializationError("NONFINITE_RAW_FIELD")
    return {"archive_member_names": names, "schema_identity": header, "timestamp_unit": "milliseconds", "raw_first_timestamp": stamps[0], "raw_last_timestamp": stamps[-1], "row_count": len(rows) - 1, "duplicate_identity_count": 0, "gap_integrity_disposition": "PASS"}


def _object(get: Any, item: dict[str, Any], cache: Path, expected_first: int | None = None, expected_last: int | None = None) -> dict[str, Any]:
    base = {k: item[k] for k in item}
    try:
        response = get(item["canonical_url"], timeout=(10, 120))
    except requests.RequestException as exc:
        return {**base, "status": "SOURCE_ACQUISITION_FAILED", "detail": type(exc).__name__}
    if response.status_code == 404:
        return {**base, "status": "SOURCE_OBJECT_NOT_PUBLISHED", "reason_class": "UPSTREAM_OBJECT_NOT_YET_PUBLISHED"}
    if response.status_code != 200:
        return {**base, "status": "SOURCE_ACQUISITION_FAILED", "http_status": response.status_code}
    payload = response.content
    local = hashlib.sha256(payload).hexdigest()
    try:
        checksum_response = get(item["checksum_url"], timeout=(10, 30))
        official = _checksum(checksum_response.text) if checksum_response.status_code == 200 else None
        if official is None or official != local:
            return {**base, "status": "CHECKSUM_VERIFICATION_FAILED", "official_checksum": official, "local_sha256": local}
        structural = _raw_check(item["source_family"], payload, expected_first or 0, expected_last or 0) if expected_first is not None else {}
    except (requests.RequestException, MaterializationError) as exc:
        return {**base, "status": "RAW_INTEGRITY_FAILED", "official_checksum": official if 'official' in locals() else None, "local_sha256": local, "detail": str(exc)}
    target = cache / f"{local}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(payload)
    return {**base, "status": "MATERIALIZED_VERIFIED", "official_checksum_algorithm": "SHA256", "official_checksum": official, "local_sha256": local, "byte_size": len(payload), **structural, "cache_path": str(CACHE_REL / target.name)}


def run(root: Path, *, get: Any = None) -> dict[str, Any]:
    request = materialization_request(root)
    out = root / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    req_path = out / "materialization_request.json"
    if (out / "materialization_receipt.json").exists():
        raise MaterializationError("materialization is already frozen; reacquisition is unauthorized")
    if req_path.exists() and json.loads(req_path.read_text()) != request:
        raise MaterializationError("GLOBAL_BLOCK: immutable materialization request changed")
    req_path.write_bytes(canonical(request) + b"\n")
    getter = get or requests.Session().get
    records: list[dict[str, Any]] = []
    for item in request["source_objects"]:
        # JFP01 is blocked at the exact missing August object census boundary;
        # no bulk download or source substitution is permitted after that fact.
        if item["candidate_id"] == "JFP01" and item["calendar_period"] == "2026-08":
            records.append({**item, "status": "SOURCE_OBJECT_NOT_PUBLISHED", "reason_class": "UPSTREAM_OBJECT_NOT_YET_PUBLISHED"})
            continue
        if item["candidate_id"] == "JFP01":
            records.append({**item, "status": "NOT_ACQUIRED_CANDIDATE_BLOCKED_BY_REQUIRED_OBJECT"})
            continue
        year, month = (int(x) for x in item["calendar_period"].split("-"))
        first_dt = datetime(year, month, 1, tzinfo=UTC)
        next_month = (first_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_dt = next_month - timedelta(hours=1)
        first = int(first_dt.timestamp() * 1000)
        last = int(last_dt.timestamp() * 1000)
        records.append(_object(getter, item, root / CACHE_REL, first, last))
    by_candidate = {c: [r for r in records if r["candidate_id"] == c] for c in CANDIDATES}
    qualifications = []
    for candidate in CANDIDATES:
        rows = by_candidate[candidate]
        blocked = any(r["status"] != "MATERIALIZED_VERIFIED" for r in rows)
        reasons = sorted({r.get("reason_class", r.get("status")) for r in rows if r["status"] != "MATERIALIZED_VERIFIED"})
        qualifications.append({"candidate_id": candidate, "disposition": "BLOCKED_CANDIDATE" if blocked else "READY", "input_integrity_only": True, "source_object_count": len(rows), "authenticated_object_count": sum(r["status"] == "MATERIALIZED_VERIFIED" for r in rows), "block_reasons": reasons})
    qualification = {"artifact_type": "JFP_INPUT_QUALIFICATION_V0", "phase_id": PHASE_ID, "ordered_candidates": qualifications, "execution_authorized": False, "input_reacquisition_authorized": False, "all_downstream_authorities": "NONE"}
    qualification["input_qualification_digest"] = digest(qualification)
    identity_rows = [{"candidate_id": r["candidate_id"], "source_family": r["source_family"], "calendar_period": r["calendar_period"], "status": r["status"], "local_sha256": r.get("local_sha256"), "official_checksum": r.get("official_checksum")} for r in records]
    snapshot_body = {"frozen_preregistration_digest": PREREG_DIGEST, "frozen_candidate_census_digest": CENSUS_DIGEST, "ordered_candidate_ids": list(CANDIDATES), "ordered_source_object_identities": identity_rows, "qualification_digest": qualification["input_qualification_digest"]}
    snapshot = {"artifact_type": "JFP_INPUT_MATERIALIZATION_SNAPSHOT_V0", "snapshot_id": "jfp-input-v0-" + digest(snapshot_body), "snapshot_digest": digest(snapshot_body), "identity_semantics": snapshot_body}
    receipt = {"artifact_type": "JFP_INPUT_MATERIALIZATION_RECEIPT_V0", "phase_id": PHASE_ID, "request_digest": request["request_digest"], "source_object_identities": records, "snapshot_id": snapshot["snapshot_id"], "snapshot_digest": snapshot["snapshot_digest"], "live_network_used": True, "scientific_computation_performed": False}
    receipt["materialization_receipt_digest"] = digest(receipt)
    (out / "per_source_manifest.json").write_bytes(canonical({"source_objects": records}) + b"\n")
    (out / "candidate_input_manifest.json").write_bytes(canonical({"candidates": qualifications}) + b"\n")
    (out / "input_qualification.json").write_bytes(canonical(qualification) + b"\n")
    (out / "snapshot_manifest.json").write_bytes(canonical(snapshot) + b"\n")
    (out / "materialization_receipt.json").write_bytes(canonical(receipt) + b"\n")
    return {"request": request, "receipt": receipt, "qualification": qualification, "snapshot": snapshot}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve()), sort_keys=True))
