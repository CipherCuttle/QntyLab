"""Exact raw-input materialization for the JH01 temporal replication.

This module is deliberately a control layer over the authenticated Binance
USD-M monthly 1h archive adapter.  It only authenticates, stores, and checks
raw OHLCV input shape.  It has no scientific transformation or execution
path.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

from . import jh01_rv_persistence_temporal_replication_prereg_v0 as prereg
from .binance_um_kline_1h import (
    CONTRACT_VERSION,
    LEGACY_FIELDS,
    SCHEMA_VERSION,
    archive_paths,
    materialize_from_objects,
    months,
    receipt_from_bytes,
)
from .market_observation import InstrumentIdentity


PHASE_ID = "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_INPUT_MATERIALIZATION_V0"
OUTPUT_RELATIVE = Path("experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization")
RAW_RELATIVE = Path("data/raw/jh01_rv_persistence_temporal_replication_v0")
ARCHIVE_RELATIVE = Path("data/archive/binance_um_kline_1h")
REQUEST_TYPE = "JH01_REPLICATION_INPUT_MATERIALIZATION_REQUEST_V0"
EXPECTED_BARS_PER_SYMBOL = 8785
DISCOVERY_SNAPSHOT_ID = prereg.SOURCE_SNAPSHOT_ID
TERMINAL_SOURCE_STATUSES = frozenset(
    {
        "MATERIALIZED_VERIFIED",
        "SOURCE_OBJECT_ABSENT",
        "SOURCE_AUTHENTICATION_UNAVAILABLE",
        "SOURCE_AUTHENTICATION_FAILED",
        "ARCHIVE_INVALID",
        "SCHEMA_INVALID",
        "IDENTITY_MISMATCH",
        "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION",
    }
)


class QualificationError(ValueError):
    """Raw input fails the frozen materialization contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise QualificationError("timezone-aware timestamp required")
    parsed = parsed.astimezone(UTC)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise QualificationError("hour-aligned timestamp required")
    return parsed


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def expected_timestamps() -> tuple[str, ...]:
    first, last = _utc(prereg.REQUIRED_FIRST_BAR_OPEN), _utc(prereg.REQUIRED_LAST_BAR_OPEN)
    values: list[str] = []
    cursor = first
    while cursor <= last:
        values.append(_stamp(cursor))
        cursor += timedelta(hours=1)
    if len(values) != EXPECTED_BARS_PER_SYMBOL:
        raise QualificationError("frozen expected timestamp cardinality drift")
    return tuple(values)


def _identity(symbol: str) -> InstrumentIdentity:
    return InstrumentIdentity(symbol, "usd-m", "perpetual", f"binance|{symbol}|perpetual|usd-m|jh01-temporal-replication-v0")


def materialization_request(root: Path) -> dict[str, Any]:
    """Build the deterministic contract identity; it excludes wall-clock data."""
    artifact = prereg.load_preregistration(root)
    prereg.validate(artifact)
    if artifact["preregistration_digest"] != "46f923023b4b696307da2b9d6fc4c8db9d04b40b012de35e0bf738cc03c4be57":
        raise QualificationError("frozen preregistration digest drift")
    value: dict[str, Any] = {
        "artifact_type": REQUEST_TYPE,
        "phase_id": PHASE_ID,
        "replication_preregistration_digest": artifact["preregistration_digest"],
        "preregistration_file_sha256": file_digest(root / prereg.ARTIFACT_RELATIVE_PATH),
        "source_piece_id": prereg.SOURCE_PIECE_ID,
        "source_snapshot_id": DISCOVERY_SNAPSHOT_ID,
        "ordered_universe": list(prereg.UNIVERSE),
        "universe_digest": prereg.universe_digest(prereg.UNIVERSE),
        "venue_contract": {"provider": "Binance", "market": "USD-M", "contract_type": "perpetual", "source_family": "data.binance.vision.monthly.klines"},
        "bar_interval": "1h",
        "first_required_bar_open": prereg.REQUIRED_FIRST_BAR_OPEN,
        "last_required_bar_open": prereg.REQUIRED_LAST_BAR_OPEN,
        "expected_bars_per_symbol": EXPECTED_BARS_PER_SYMBOL,
        "input_integrity_rules": {
            "timestamp_set": "EXACT_INCLUSIVE_HOURLY_SET",
            "duplicate_policy": "REJECT",
            "missing_policy": "REJECT",
            "required_schema": list(LEGACY_FIELDS),
            "required_raw_prices": "FINITE_AND_STRICTLY_POSITIVE",
            "source_authentication": "PUBLISHED_CHECKSUM_SHA256_MATCHES_ZIP_BYTES",
        },
        "provenance_requirements": "preserve authenticated source-object digests and deterministic accepted-content digests",
        "scientific_execution_prohibited": True,
        "transport_policy": {"attempts_per_object_url": 1, "retry_policy": "NO_RETRY; one bounded live materialization"},
    }
    value["request_digest"] = digest(value)
    return value


def _finite_positive(value: object) -> bool:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and parsed > 0


def qualify_symbol(symbol: str, rows: list[Mapping[str, str]], *, source_object_digests: list[str], raw_content_digest: str | None, source_objects_authenticated: bool = True) -> dict[str, Any]:
    """Check one admitted raw bar collection without deriving any research values."""
    expected = expected_timestamps()
    reasons: list[str] = []
    timestamps: list[str] = []
    schema_valid = True
    finite_positive = True
    for row in rows:
        if set(row) != set(LEGACY_FIELDS):
            schema_valid = False
            continue
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, str):
            schema_valid = False
            continue
        timestamps.append(timestamp)
        if any(not _finite_positive(row.get(field)) for field in ("open", "high", "low", "close")):
            finite_positive = False
    unique = set(timestamps)
    expected_set = set(expected)
    duplicate_count = len(timestamps) - len(unique)
    missing = sorted(expected_set - unique)
    unexpected = sorted(unique - expected_set)
    monotonic = timestamps == sorted(timestamps)
    actual_first = timestamps[0] if timestamps else None
    actual_last = timestamps[-1] if timestamps else None
    if not schema_valid:
        reasons.append("SCHEMA_INVALID")
    if duplicate_count:
        reasons.append("DUPLICATE_REQUIRED_TIMESTAMP")
    if missing:
        reasons.append("MISSING_REQUIRED_HOUR")
    if unexpected:
        reasons.append("UNEXPECTED_HOUR")
    if not monotonic:
        reasons.append("TIMESTAMPS_NOT_MONOTONIC")
    if actual_first != prereg.REQUIRED_FIRST_BAR_OPEN or actual_last != prereg.REQUIRED_LAST_BAR_OPEN:
        reasons.append("RAW_COVERAGE_ENDPOINT_MISMATCH")
    if len(unique) != EXPECTED_BARS_PER_SYMBOL:
        reasons.append("RAW_BAR_COUNT_MISMATCH")
    if not finite_positive:
        reasons.append("NONFINITE_OR_NONPOSITIVE_RAW_PRICE")
    if raw_content_digest is None or len(raw_content_digest) != 64:
        reasons.append("SOURCE_CONTENT_DIGEST_UNAVAILABLE")
    if not source_objects_authenticated:
        reasons.append("SOURCE_PROVENANCE_UNAUTHENTICATED")
    result = {
        "symbol": symbol,
        "source_provider": "Binance data.binance.vision",
        "market": "usd-m",
        "contract_type": "perpetual",
        "interval": "1h",
        "requested_first_bar_open": prereg.REQUIRED_FIRST_BAR_OPEN,
        "requested_last_bar_open": prereg.REQUIRED_LAST_BAR_OPEN,
        "actual_first_bar_open": actual_first,
        "actual_last_bar_open": actual_last,
        "expected_bar_count": EXPECTED_BARS_PER_SYMBOL,
        "actual_unique_bar_count": len(unique),
        "duplicate_count": duplicate_count,
        "missing_hour_count": len(missing),
        "unexpected_hour_count": len(unexpected),
        "schema_valid": schema_valid,
        "timestamps_monotonic": monotonic,
        "timestamps_unique": duplicate_count == 0,
        "all_required_timestamps_present": not missing,
        "required_raw_prices_finite": finite_positive,
        "required_raw_prices_strictly_positive": finite_positive,
        "ordered_source_object_digests": source_object_digests,
        "source_objects_authenticated": source_objects_authenticated,
        "accepted_raw_content_sha256": raw_content_digest,
        "qualification": "PASS" if not reasons else "BLOCKED",
        "block_reasons": reasons,
    }
    result["qualification_digest"] = digest(result)
    return result


def qualify_panel(per_symbol: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    symbols = list(per_symbol)
    reasons: list[str] = []
    if symbols != list(prereg.UNIVERSE):
        reasons.append("EXACT_ORDERED_UNIVERSE_MISMATCH")
    if len(symbols) != len(prereg.UNIVERSE):
        reasons.append("EXACT_PANEL_CARDINALITY_MISMATCH")
    passed = sum(record.get("qualification") == "PASS" for record in per_symbol.values())
    if passed != len(prereg.UNIVERSE):
        reasons.append("ONE_OR_MORE_SYMBOLS_BLOCKED")
    status = "INPUT_READY" if not reasons else "BLOCKED_BY_INPUT_CONTRACT"
    value = {
        "artifact_type": "JH01_REPLICATION_INPUT_QUALIFICATION_V0",
        "phase_id": PHASE_ID,
        "ordered_universe": list(prereg.UNIVERSE),
        "universe_digest": prereg.universe_digest(prereg.UNIVERSE),
        "expected_symbols": len(prereg.UNIVERSE),
        "observed_symbol_records": len(symbols),
        "pass_count": passed,
        "blocked_count": len(symbols) - passed,
        "qualification_status": status,
        "input_ready": status == "INPUT_READY",
        "block_reasons": reasons,
        "per_symbol": [per_symbol[symbol] for symbol in symbols],
        "scientific_replication_claim": "NOT_EXECUTED",
        "jigsaw_evidence_created": False,
        "execution_authorized": False,
        "state_snapshot_authorized": False,
    }
    value["input_qualification_digest"] = digest(value)
    return value


def temporal_independence() -> dict[str, Any]:
    return prove_temporal_independence("2025-06-20T00:00:00Z", prereg.REQUIRED_FIRST_BAR_OPEN)


def prove_temporal_independence(discovery_final_future_close: str, replication_raw_first: str) -> dict[str, Any]:
    discovery_last = _utc(discovery_final_future_close)
    replication_first = _utc(replication_raw_first)
    independent = replication_first > discovery_last
    if not independent:
        raise QualificationError("REPLICATION_OVERLAPS_DISCOVERY_HISTORY")
    return {
        "discovery_decision_overlap": False,
        "discovery_outcome_overlap": False,
        "replication_evaluation_history_reuse": False,
        "proof": "replication raw coverage begins after the discovery final future-outcome close boundary",
        "independent_temporal_input_sample_established": independent,
        "independent_empirical_replication_established": False,
    }


def snapshot_manifest(request: Mapping[str, Any], qualification: Mapping[str, Any]) -> dict[str, Any]:
    semantics = {
        "request_digest": request["request_digest"],
        "ordered_universe": qualification["ordered_universe"],
        "per_symbol_accepted_raw_content_sha256": [record["accepted_raw_content_sha256"] for record in qualification["per_symbol"]],
        "per_symbol_source_object_digests": [record["ordered_source_object_digests"] for record in qualification["per_symbol"]],
        "first_required_bar_open": prereg.REQUIRED_FIRST_BAR_OPEN,
        "last_required_bar_open": prereg.REQUIRED_LAST_BAR_OPEN,
        "interval": "1h",
        "provider_contract": request["venue_contract"],
        "qualification_status": qualification["qualification_status"],
    }
    snapshot_digest = digest(semantics)
    if snapshot_digest == prereg.SOURCE_SNAPSHOT_DIGEST:
        raise QualificationError("discovery snapshot identity reuse")
    return {
        "artifact_type": "JH01_REPLICATION_INPUT_SNAPSHOT_MANIFEST_V0",
        "snapshot_id": f"jh01-rv-temporal-input-v0-{snapshot_digest}",
        "snapshot_digest": snapshot_digest,
        "discovery_snapshot_id": DISCOVERY_SNAPSHOT_ID,
        "discovery_snapshot_alias": False,
        "identity_semantics": semantics,
        "temporal_independence": temporal_independence(),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def write_static_request(root: Path) -> Path:
    target = root / OUTPUT_RELATIVE / "materialization_request.json"
    request = materialization_request(root)
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != request:
        raise QualificationError("existing immutable materialization request differs")
    _write_json(target, request)
    return target


def _source_receipt(symbol: str, year: int, month: int, status: str, *, zip_bytes: bytes | None = None, detail: str | None = None) -> dict[str, Any]:
    paths = archive_paths(symbol, year, month)
    value = {
        "symbol": symbol,
        "year": year,
        "month": month,
        "interval": "1h",
        "source_family": "data.binance.vision.monthly.klines",
        **paths,
        "status": status,
        "actual_raw_sha256": hashlib.sha256(zip_bytes).hexdigest() if zip_bytes is not None else None,
        "detail": detail,
    }
    value["receipt_digest"] = digest(value)
    return value


def materialize_live(root: Path, *, get: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Perform the single bounded network acquisition, then persist its evidence."""
    output = root / OUTPUT_RELATIVE
    receipt_path = output / "materialization_receipt.json"
    if receipt_path.exists():
        raise QualificationError("live materialization already frozen; a second acquisition is prohibited")
    request_path = write_static_request(root)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("request_digest") != digest({key: value for key, value in request.items() if key != "request_digest"}):
        raise QualificationError("materialization request digest mismatch")
    getter = get or requests.Session().get
    cache = root / ARCHIVE_RELATIVE
    raw_root = root / RAW_RELATIVE
    all_source_receipts: list[dict[str, Any]] = []
    per_symbol: dict[str, dict[str, Any]] = {}
    source_objects_by_symbol: dict[str, dict[tuple[int, int], tuple[bytes | None, str | None]]] = {}
    acquisition_failures: dict[str, list[str]] = {}
    for symbol in prereg.UNIVERSE:
        identity = _identity(symbol)
        objects: dict[tuple[int, int], tuple[bytes | None, str | None]] = {}
        receipts: list[dict[str, Any]] = []
        failures: list[str] = []
        for year, month in months(prereg.REQUIRED_FIRST_BAR_OPEN, prereg.REQUIRED_LAST_BAR_OPEN):
            paths = archive_paths(symbol, year, month)
            try:
                archive_response = getter(paths["zip_url"], timeout=(10, 90))
            except requests.RequestException as exc:
                receipt = _source_receipt(symbol, year, month, "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION", detail=type(exc).__name__)
                objects[(year, month)] = (None, None); failures.append(receipt["status"])
            else:
                if archive_response.status_code == 404:
                    receipt = _source_receipt(symbol, year, month, "SOURCE_OBJECT_ABSENT")
                    objects[(year, month)] = (None, None)
                elif archive_response.status_code != 200:
                    receipt = _source_receipt(symbol, year, month, "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION", detail=f"HTTP_{archive_response.status_code}")
                    objects[(year, month)] = (None, None); failures.append(receipt["status"])
                else:
                    zip_bytes = archive_response.content
                    try:
                        checksum_response = getter(paths["checksum_url"], timeout=(10, 30))
                    except requests.RequestException as exc:
                        receipt = _source_receipt(symbol, year, month, "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION", zip_bytes=zip_bytes, detail=type(exc).__name__)
                        objects[(year, month)] = (zip_bytes, None); failures.append(receipt["status"])
                    else:
                        checksum = checksum_response.text if checksum_response.status_code == 200 else None
                        try:
                            verified, _ = receipt_from_bytes(symbol, year, month, zip_bytes, checksum or "", identity)
                            receipt = {key: value for key, value in verified.items() if key != "retrieved_at"}
                            receipt["receipt_digest"] = digest({key: value for key, value in receipt.items() if key != "receipt_digest"})
                            objects[(year, month)] = (zip_bytes, checksum)
                            cache.mkdir(parents=True, exist_ok=True)
                            (cache / f"{receipt['actual_raw_sha256']}.zip").write_bytes(zip_bytes)
                        except Exception as exc:
                            receipt = _source_receipt(symbol, year, month, getattr(exc, "status", "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION"), zip_bytes=zip_bytes, detail=type(exc).__name__)
                            objects[(year, month)] = (zip_bytes, checksum)
                            if receipt["status"] == "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION":
                                failures.append(receipt["status"])
            if receipt["status"] not in TERMINAL_SOURCE_STATUSES:
                raise QualificationError("nonterminal source receipt")
            receipts.append(receipt); all_source_receipts.append(receipt)
        source_objects_by_symbol[symbol] = objects
        acquisition_failures[symbol] = failures
        adapter = materialize_from_objects(symbol, prereg.REQUIRED_FIRST_BAR_OPEN, prereg.REQUIRED_LAST_BAR_OPEN, objects, identity, "jh01-rv-temporal-input-v0")
        rows: list[Mapping[str, str]] = []
        raw_digest: str | None = None
        if adapter["status"] == "MATERIALIZED_VERIFIED":
            raw_csv = adapter["normalized_csv"]
            raw_digest = hashlib.sha256(raw_csv.encode("utf-8")).hexdigest()
            raw_root.mkdir(parents=True, exist_ok=True)
            (raw_root / f"{symbol}-perp-1h.csv").write_text(raw_csv, encoding="utf-8")
            rows = list(csv.DictReader(StringIO(raw_csv)))
        source_authenticated = all(
            item["status"] == "MATERIALIZED_VERIFIED" and item.get("published_sha256") == item.get("actual_raw_sha256")
            for item in receipts
        )
        record = qualify_symbol(symbol, rows, source_object_digests=[item["receipt_digest"] for item in receipts], raw_content_digest=raw_digest, source_objects_authenticated=source_authenticated)
        record["materialized_object_reference"] = str((RAW_RELATIVE / f"{symbol}-perp-1h.csv")) if raw_digest else None
        record["qualification_digest"] = digest({key: value for key, value in record.items() if key != "qualification_digest"})
        if failures:
            record["qualification"] = "BLOCKED"
            record["block_reasons"] = sorted(set([*record["block_reasons"], "BLOCKED_BY_INPUT_ACQUISITION_IMPLEMENTATION"]))
            record["qualification_digest"] = digest({key: value for key, value in record.items() if key != "qualification_digest"})
        per_symbol[symbol] = record
    qualification = qualify_panel(per_symbol)
    panel_unavailable_established = "NO" if any(acquisition_failures.values()) else ("YES" if qualification["qualification_status"] != "INPUT_READY" else "NOT_APPLICABLE")
    receipt = {
        "artifact_type": "JH01_REPLICATION_INPUT_MATERIALIZATION_RECEIPT_V0",
        "phase_id": PHASE_ID,
        "request_digest": request["request_digest"],
        "source_provider": "Binance data.binance.vision",
        "source_transport": "authenticated monthly ZIP plus published CHECKSUM",
        "live_network_used": True,
        "bounded_retry_policy": request["transport_policy"],
        "source_object_count": len(all_source_receipts),
        "source_receipts": all_source_receipts,
        "panel_unavailable_established": panel_unavailable_established,
        "secrets_recorded": False,
    }
    receipt["materialization_receipt_digest"] = digest(receipt)
    snapshot = snapshot_manifest(request, qualification)
    _write_json(output / "per_symbol_manifest.json", {"artifact_type": "JH01_PER_SYMBOL_INPUT_MANIFEST_V0", "request_digest": request["request_digest"], "per_symbol": [per_symbol[s] for s in prereg.UNIVERSE]})
    _write_json(output / "input_qualification.json", qualification)
    _write_json(output / "snapshot_manifest.json", snapshot)
    _write_json(receipt_path, receipt)
    return {"request": request, "receipt": receipt, "qualification": qualification, "snapshot": snapshot}


def refresh_derived_artifacts(root: Path) -> dict[str, Any]:
    """Rebuild derived qualification files from frozen local raw bytes only.

    This performs no transport operation and refuses to alter the immutable
    source receipt.  It exists solely to make review-time integrity checks
    reproducible before the materialization candidate is frozen.
    """
    output = root / OUTPUT_RELATIVE
    request = json.loads((output / "materialization_request.json").read_text(encoding="utf-8"))
    receipt = json.loads((output / "materialization_receipt.json").read_text(encoding="utf-8"))
    if request.get("request_digest") != digest({key: value for key, value in request.items() if key != "request_digest"}):
        raise QualificationError("materialization request digest mismatch")
    if receipt.get("materialization_receipt_digest") != digest({key: value for key, value in receipt.items() if key != "materialization_receipt_digest"}):
        raise QualificationError("materialization receipt digest mismatch")
    receipts_by_symbol: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in prereg.UNIVERSE}
    for source in receipt.get("source_receipts", []):
        if source.get("symbol") in receipts_by_symbol:
            receipts_by_symbol[source["symbol"]].append(source)
    per_symbol: dict[str, dict[str, Any]] = {}
    for symbol in prereg.UNIVERSE:
        raw_path = root / RAW_RELATIVE / f"{symbol}-perp-1h.csv"
        rows = list(csv.DictReader(StringIO(raw_path.read_text(encoding="utf-8")))) if raw_path.is_file() else []
        raw_digest = file_digest(raw_path) if raw_path.is_file() else None
        sources = receipts_by_symbol[symbol]
        authenticated = bool(sources) and all(
            source.get("status") == "MATERIALIZED_VERIFIED" and source.get("published_sha256") == source.get("actual_raw_sha256")
            for source in sources
        )
        record = qualify_symbol(symbol, rows, source_object_digests=[source["receipt_digest"] for source in sources], raw_content_digest=raw_digest, source_objects_authenticated=authenticated)
        record["materialized_object_reference"] = str(RAW_RELATIVE / f"{symbol}-perp-1h.csv") if raw_digest else None
        record["qualification_digest"] = digest({key: value for key, value in record.items() if key != "qualification_digest"})
        per_symbol[symbol] = record
    qualification = qualify_panel(per_symbol)
    snapshot = snapshot_manifest(request, qualification)
    _write_json(output / "per_symbol_manifest.json", {"artifact_type": "JH01_PER_SYMBOL_INPUT_MANIFEST_V0", "request_digest": request["request_digest"], "per_symbol": [per_symbol[s] for s in prereg.UNIVERSE]})
    _write_json(output / "input_qualification.json", qualification)
    _write_json(output / "snapshot_manifest.json", snapshot)
    return {"qualification": qualification, "snapshot": snapshot}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write-request", action="store_true")
    parser.add_argument("--materialize-live", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write_request:
        print(write_static_request(root))
    if args.materialize_live:
        print(json.dumps(materialize_live(root), sort_keys=True))


if __name__ == "__main__":
    main()
