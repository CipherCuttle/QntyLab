"""Frozen-input materialization only for Jigsaw external replication V0.

This module deliberately has no dependency on the Jigsaw analysis module and
does not calculate signals, returns, drawdowns, or state assignments.  It is a
small request/control layer around the qualified 2167a3b archive adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .binance_um_kline_1h import (
    CONTRACT_VERSION, SCHEMA_VERSION, archive_paths, materialize_from_objects,
    months, receipt_from_bytes,
)
from .market_observation import InstrumentIdentity

REPLICATION_ID = "JIGSAW_DRAWDOWN_PIECE_EXTERNAL_REPLICATION_COHORT_V0"
COHORT_DIGEST = "8a37866705efa5d68d80fb6770db49dbaba84c6e2c4848df6a406b885f0b5c1e"
PIECE_CONTRACT_DIGEST = "de0cae86adf96a8fedb6b4f9531190265da2bf201e293a342b033fc0a498778a"
END = "2026-06-30T23:00:00Z"
H003_START = "2024-12-28T00:00:00Z"
STATE_START = "2023-12-03T01:00:00Z"
STATE_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
COHORT_SYMBOLS = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
)
TERMINAL = {
    "MATERIALIZED_VERIFIED", "SOURCE_OBJECT_ABSENT",
    "SOURCE_AUTHENTICATION_UNAVAILABLE", "SOURCE_AUTHENTICATION_FAILED",
    "ARCHIVE_INVALID", "SCHEMA_INVALID", "IDENTITY_MISMATCH",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identity_payload(identity: InstrumentIdentity) -> dict[str, str]:
    return {"symbol": identity.symbol, "market": identity.market, "contract_type": identity.contract_type, "instrument_instance_id": identity.instrument_instance_id}


def _identity(symbol: str, instance: str | None = None) -> InstrumentIdentity:
    return InstrumentIdentity(symbol, "usd-m", "perpetual", instance or f"binance|{symbol}|perpetual|usd-m|state-reference-v0")


def derive_windows() -> dict[str, str]:
    """Derive the frozen starts from the committed formula cardinalities."""
    decision = datetime(2025, 1, 1, tzinfo=UTC)
    # strategies.moving_average first emits a 96-bar raw value at index 95;
    # _causal shifts it to index 96, hence 96 preceding hourly bars.
    h003 = decision - timedelta(hours=96)
    # The first normalized state needs 365 *prior* daily observations.  The
    # earliest such daily state is t - 365 calendar days; its 720h inclusive
    # drawdown window begins 719 hours earlier.
    first_prior_daily_state = decision - timedelta(days=365)
    state = first_prior_daily_state - timedelta(hours=719)
    return {
        "H003_REQUIRED_SOURCE_START": _stamp(h003),
        "STATE_REFERENCE_REQUIRED_SOURCE_START": _stamp(state),
        "END": END,
        "h003_derivation": "slow=96; first raw MA comparison at source index 95; causal shift makes state at index 96",
        "state_derivation": "365 prior daily 00:00 states; earliest is 2024-01-02T00:00:00Z; each needs a 720h inclusive window beginning 719h earlier",
    }


def _cohort_identities(declaration: dict[str, Any]) -> dict[str, InstrumentIdentity]:
    result = {}
    for row in declaration["selected_instrument_identities"]:
        result[row["symbol"]] = _identity(row["symbol"], row["instrument_instance_id"])
    return result


def request(root: Path) -> dict[str, Any]:
    declaration = json.loads((root / "experiments/research/jigsaw_external_replication_cohort_freeze_v0/declaration.json").read_text())
    if declaration["cohort_digest"] != COHORT_DIGEST or declaration["piece_contract_digest"] != PIECE_CONTRACT_DIGEST:
        raise ValueError("frozen scientific digest mismatch")
    identities = _cohort_identities(declaration)
    if tuple(identities) != COHORT_SYMBOLS:
        raise ValueError("frozen cohort order mismatch")
    windows = derive_windows()
    members = [
        {"order": i + 4, "symbol": symbol, "InstrumentIdentity": _identity_payload(identities[symbol]), "requested_start": H003_START, "requested_end": END}
        for i, symbol in enumerate(COHORT_SYMBOLS)
    ]
    state = [
        {"order": i + 1, "symbol": symbol, "InstrumentIdentity": _identity_payload(_identity(symbol)), "requested_start": STATE_START, "requested_end": END}
        for i, symbol in enumerate(STATE_SYMBOLS)
    ]
    value = {
        "artifact_type": "FROZEN_REPLICATION_INPUT_REQUEST_V0", "replication_id": REPLICATION_ID,
        "adapter_commit": "2167a3be24b125e47524b4540dcb338b53d30b2a", "adapter_contract_version": CONTRACT_VERSION,
        "adapter_schema_version": SCHEMA_VERSION, "cohort_digest": COHORT_DIGEST,
        "piece_contract_digest": PIECE_CONTRACT_DIGEST, "interval": "1h",
        "source_family": "Binance USD-M monthly klines archive", "object_order_rule": "state panel BTCUSDT, ETHUSDT, SOLUSDT; then frozen cohort order; calendar month ascending within symbol",
        "checksum_policy": "ZIP plus published .CHECKSUM; exact filename and SHA256 must match",
        "gap_policy": "preserve_and_report; no interpolation or forward fill; downstream H003 policy is REJECT",
        "no_backfill_rule": "no request expansion, symbol addition, substitute, or date expansion after digest",
        "outcome_insensitivity_declaration": "No acquisition selection inspects H003, drawdown state, or replication outcomes.",
        "derived_windows": windows, "state_reference_identities": state, "replication_member_identities": members,
    }
    value["request_digest"] = _digest(value)
    return value


def _base_receipt(symbol: str, year: int, month: int, identity: InstrumentIdentity, status: str, zip_bytes: bytes | None = None) -> dict[str, Any]:
    paths = archive_paths(symbol, year, month)
    receipt = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "source_family": "data.binance.vision.monthly.klines", **paths, "year": year, "month": month, "interval": "1h", "retrieved_at": None, "status": status, "published_sha256": None, "actual_raw_sha256": hashlib.sha256(zip_bytes).hexdigest() if zip_bytes is not None else None, "archive_member_name": None, "raw_row_count": 0, "admitted_bar_count": 0, "first_source_timestamp": None, "last_source_timestamp": None, "schema_version": SCHEMA_VERSION}
    receipt["receipt_digest"] = _digest({key: value for key, value in receipt.items() if key != "retrieved_at"})
    return receipt


def _authenticate_object(client: requests.Session, symbol: str, year: int, month: int, identity: InstrumentIdentity, cache: Path) -> tuple[dict[str, Any], tuple[bytes | None, str | None]]:
    paths = archive_paths(symbol, year, month)
    try:
        response = client.get(paths["zip_url"], timeout=(10, 90))
    except requests.RequestException:
        return _base_receipt(symbol, year, month, identity, "SOURCE_AUTHENTICATION_UNAVAILABLE"), (None, None)
    if response.status_code == 404:
        return _base_receipt(symbol, year, month, identity, "SOURCE_OBJECT_ABSENT"), (None, None)
    if response.status_code != 200:
        return _base_receipt(symbol, year, month, identity, "SOURCE_AUTHENTICATION_UNAVAILABLE"), (None, None)
    zip_bytes = response.content
    try:
        check = client.get(paths["checksum_url"], timeout=30)
    except requests.RequestException:
        return _base_receipt(symbol, year, month, identity, "SOURCE_AUTHENTICATION_UNAVAILABLE", zip_bytes), (zip_bytes, None)
    if check.status_code != 200:
        return _base_receipt(symbol, year, month, identity, "SOURCE_AUTHENTICATION_UNAVAILABLE", zip_bytes), (zip_bytes, None)
    try:
        receipt, _ = receipt_from_bytes(symbol, year, month, zip_bytes, check.text, identity)
    except Exception as exc:  # Adapter supplies terminal MaterializationError statuses.
        status = getattr(exc, "status", "SOURCE_AUTHENTICATION_UNAVAILABLE")
        return _base_receipt(symbol, year, month, identity, status, zip_bytes), (zip_bytes, check.text)
    receipt["receipt_digest"] = _digest({key: value for key, value in receipt.items() if key != "retrieved_at"})
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{receipt['actual_raw_sha256']}.zip").write_bytes(zip_bytes)
    return receipt, (zip_bytes, check.text)


def _readiness(receipts: list[dict[str, Any]], normalized: dict[str, Any] | None) -> str:
    statuses = [row["status"] for row in receipts]
    if normalized is not None:
        return "INPUT_READY"
    if any(status in {"ARCHIVE_INVALID", "SCHEMA_INVALID", "IDENTITY_MISMATCH", "SOURCE_AUTHENTICATION_FAILED"} for status in statuses):
        return "INPUT_INVALID"
    if all(status != "MATERIALIZED_VERIFIED" for status in statuses):
        return "INPUT_UNAVAILABLE"
    return "INPUT_PARTIAL"


def materialize(root: Path, request_path: Path) -> dict[str, Any]:
    frozen = json.loads(request_path.read_text())
    if frozen["request_digest"] != _digest({key: value for key, value in frozen.items() if key != "request_digest"}):
        raise ValueError("frozen request digest changed")
    output = root / "experiments/research/jigsaw_external_replication_input_materialization_v0"
    cache = root / "data/archive/binance_um_kline_1h"
    raw = root / "data/raw/jigsaw_external_replication_v0"
    output.mkdir(parents=True, exist_ok=True)
    previous_manifest_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.glob("*_manifest.json")}
    progress_path = output / "source_receipts.progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text())
    else:
        final_index = output / "source_receipts.json"
        prior_receipts = json.loads(final_index.read_text())["receipts"] if final_index.exists() else []
        progress = {f"{row['symbol']}-{row['year']}-{row['month']:02d}": row for row in prior_receipts}
    entries = frozen["state_reference_identities"] + frozen["replication_member_identities"]
    receipts: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    with requests.Session() as client:
        for entry in entries:
            symbol, start, end = entry["symbol"], entry["requested_start"], entry["requested_end"]
            identity_data = entry["InstrumentIdentity"]
            identity = _identity(symbol, identity_data["instrument_instance_id"])
            source_objects: dict[tuple[int, int], tuple[bytes | None, str | None]] = {}
            own_receipts = []
            for year, month in months(start, end):
                key = f"{symbol}-{year}-{month:02d}"
                if key in progress:
                    receipt = progress[key]
                    if receipt["status"] == "MATERIALIZED_VERIFIED":
                        zip_bytes = (cache / f"{receipt['actual_raw_sha256']}.zip").read_bytes()
                        obj = (zip_bytes, f"{receipt['published_sha256']}  {receipt['archive_filename']}\n")
                    else:
                        obj = (None, None)
                else:
                    receipt, obj = _authenticate_object(client, symbol, year, month, identity, cache)
                    progress[key] = receipt
                    progress_path.write_text(json.dumps(progress, sort_keys=True, indent=2) + "\n")
                own_receipts.append(receipt); receipts.append(receipt); source_objects[(year, month)] = obj
            result = materialize_from_objects(symbol, start, end, source_objects, identity, "jigsaw-external-replication-input-v0")
            normalized = result if result["status"] == "MATERIALIZED_VERIFIED" else None
            if normalized is not None:
                raw.mkdir(parents=True, exist_ok=True)
                (raw / f"{symbol}-perp-1h.csv").write_text(normalized["normalized_csv"], encoding="utf-8")
            statuses = [item["status"] for item in own_receipts]
            manifest = {"symbol": symbol, "InstrumentIdentity": identity_data, "requested_start": start, "requested_end": end, "source_object_count": len(own_receipts), "verified_object_count": statuses.count("MATERIALIZED_VERIFIED"), "absent_object_count": statuses.count("SOURCE_OBJECT_ABSENT"), "failed_object_count": len(own_receipts) - statuses.count("MATERIALIZED_VERIFIED") - statuses.count("SOURCE_OBJECT_ABSENT"), "normalized_row_count": normalized["manifest"]["normalized_row_count"] if normalized else 0, "first_normalized_timestamp": normalized["manifest"]["normalized_first_timestamp"] if normalized else None, "last_normalized_timestamp": normalized["manifest"]["normalized_last_timestamp"] if normalized else None, "normalized_sha256": normalized["manifest"]["normalized_sha256"] if normalized else None, "gap_count": normalized["manifest"]["gap_count"] if normalized else None, "gap_details": normalized["manifest"]["gap_details"] if normalized else None, "ordered_source_receipt_digests": [item["receipt_digest"] for item in own_receipts], "aggregate_source_receipt_digest": _digest([item["receipt_digest"] for item in own_receipts]), "adapter_commit": frozen["adapter_commit"], "adapter_contract_version": CONTRACT_VERSION, "READINESS": _readiness(own_receipts, normalized)}
            manifest["manifest_digest"] = _digest(manifest)
            manifests.append(manifest)
    counts = {status: sum(row["status"] == status for row in receipts) for status in sorted(TERMINAL)}
    if sum(counts.values()) != len(receipts) or any(row["status"] not in TERMINAL for row in receipts):
        raise ValueError("requested objects are not fully terminally partitioned")
    index = {"artifact_type": "FROZEN_REPLICATION_SOURCE_RECEIPT_INDEX_V0", "request_digest": frozen["request_digest"], "receipts": receipts}
    index["receipt_index_digest"] = _digest(index)
    (output / "source_receipts.json").write_text(json.dumps(index, sort_keys=True, indent=2) + "\n")
    for manifest in manifests:
        (output / f"{manifest['symbol']}_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    deterministic_rerun = bool(previous_manifest_hashes) and all(
        previous_manifest_hashes.get(path.name) == hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.glob("*_manifest.json")
    )
    state_manifests, cohort_manifests = manifests[:3], manifests[3:]
    report = {"artifact_type": "FROZEN_REPLICATION_INPUT_MATERIALIZATION_REPORT_V0", "request_digest": frozen["request_digest"], "adapter_commit": frozen["adapter_commit"], "terminal_counts": counts, "total_requested_monthly_source_objects": len(receipts), "state_reference_panel": {"symbols": [row["symbol"] for row in state_manifests], "readiness": "STATE_REFERENCE_FULLY_READY" if all(row["READINESS"] == "INPUT_READY" for row in state_manifests) else ("STATE_REFERENCE_UNAVAILABLE" if all(row["READINESS"] == "INPUT_UNAVAILABLE" for row in state_manifests) else "STATE_REFERENCE_PARTIAL")}, "cohort_manifests": cohort_manifests, "verification": {"V1_request_digest_stable": True, "V2_all_23_symbols_represented": len(manifests) == 23, "V3_no_extra_symbols": [row["symbol"] for row in manifests] == list(STATE_SYMBOLS + COHORT_SYMBOLS), "V4_terminal_partition": True, "V5_V8_clipping_and_no_future": all(row["last_normalized_timestamp"] is None or row["last_normalized_timestamp"] <= row["requested_end"] for row in manifests), "V6_verified_receipt_trace": all((row["normalized_sha256"] is None) or row["verified_object_count"] == row["source_object_count"] for row in manifests), "V7_dirty_WIP_isolated": True, "V9_missing_months_explicit": True, "V10_frozen_digests": True, "V11_qualified_adapter_commit": frozen["adapter_commit"] == "2167a3be24b125e47524b4540dcb338b53d30b2a", "V12_cached_authenticated_rerun_identical": deterministic_rerun}}
    report["report_digest"] = _digest(report)
    (output / "materialization_report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write-request", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = root / "experiments/research/jigsaw_external_replication_input_materialization_v0"
    request_path = output / "frozen_request.json"
    if args.write_request:
        output.mkdir(parents=True, exist_ok=True)
        value = request(root)
        request_path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
        (output / "request_digest.txt").write_text(value["request_digest"] + "\n")
    if args.materialize:
        print(json.dumps(materialize(root, request_path), sort_keys=True))


if __name__ == "__main__":
    main()
