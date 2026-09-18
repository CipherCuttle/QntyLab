"""DEV-only materialization for QntySpot Ink Stage B.

This module is intentionally unable to authorize candidate evaluation or OUTER
access. Real network execution is allowed only from clean canonical master via
the same Stage-B authority gate used by source qualification, and only after
two distinct source-qualification receipts agree exactly on material identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from qntylab import qntyspot_ink_source_qualification_v1 as qualification


PROJECT_ID = qualification.PROJECT_ID
POOL = qualification.POOL
SYNC_TOPIC = qualification.SYNC_TOPIC
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
PREREGISTRATION_DIGEST = "27ce60c68133f40d9496df1db6009de07957ed8a9bd68b0715cc6c54fe05d18a"
QNTYSPOT_SOURCE_SHA = "b9a84c59bd43e7697ee970d2a7571647e5de4501"
AUTHORIZATION_PATH = Path(
    "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json"
)
HISTORICAL_ACTIVATION_PATH = Path(
    "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_activation_v0/activation.json"
)
DEFAULT_QUERY_SPAN = 10_000
DEFAULT_COVERAGE_WORKERS = 2
MAX_COVERAGE_WORKERS = 8
DEFAULT_BLOCK_WORKERS = 4
MAX_BLOCK_WORKERS = 8
GAS_RECEIPT_THRESHOLD = 30
GAS_SAMPLE_MAX = 30


class AcquisitionError(RuntimeError):
    """Fail-closed DEV materialization error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"expected JSON object: {path}")
    return value


def _validate_qualification_pair(
    primary: Mapping[str, Any], secondary: Mapping[str, Any]
) -> None:
    for label, receipt in (("primary", primary), ("secondary", secondary)):
        if receipt.get("artifact_type") != "QNTYSPOT_INK_SOURCE_QUALIFICATION_RECEIPT_V1":
            raise AcquisitionError(f"{label} qualification receipt type mismatch")
        receipt_digest = receipt.get("receipt_digest")
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            raise AcquisitionError(f"{label} qualification receipt digest is missing")
        payload = dict(receipt)
        payload.pop("receipt_digest", None)
        if qualification._digest(payload) != receipt_digest:
            raise AcquisitionError(f"{label} qualification receipt digest mismatch")
        if receipt.get("status") != "PASS":
            raise AcquisitionError(f"{label} source qualification did not PASS")
        if receipt.get("outer_access_performed") is not False:
            raise AcquisitionError(f"{label} qualification receipt indicates OUTER access")
        if receipt.get("candidate_evaluation_performed") is not False:
            raise AcquisitionError(f"{label} qualification receipt indicates candidate evaluation")
    if primary.get("provider_id") == secondary.get("provider_id"):
        raise AcquisitionError("qualification receipts must come from distinct providers")
    try:
        qualification.compare_sources(primary, secondary)
    except qualification.QualificationError as exc:
        raise AcquisitionError(str(exc)) from exc


def _event_identity(log: Mapping[str, Any]) -> dict[str, Any]:
    return qualification._event_identity(log)


def _event_key(log: Mapping[str, Any]) -> tuple[int, int, int]:
    return qualification._log_order_key(log)


def _validate_log_shape(
    log: Mapping[str, Any],
    *,
    topic: str,
    start: int,
    end: int,
) -> None:
    if qualification._norm_address(log.get("address")) != qualification._norm_address(POOL):
        raise AcquisitionError("provider returned a log for the wrong pool")
    topics = log.get("topics")
    if (
        not isinstance(topics, list)
        or not topics
        or not isinstance(topics[0], str)
        or topics[0].lower() != topic
    ):
        raise AcquisitionError("provider returned a log for the wrong event topic")
    block_number = qualification._hex_int(log.get("blockNumber"))
    if not start <= block_number <= end:
        raise AcquisitionError("provider over-returned a log outside the DEV request")
    qualification._log_identity(log)
    qualification._log_order_key(log)


def _fetch_topic_chunk(
    rpc: qualification.RpcCall,
    *,
    topic: str,
    start: int,
    end: int,
) -> list[Mapping[str, Any]]:
    value = rpc(
        "eth_getLogs",
        [{
            "address": POOL,
            "fromBlock": hex(start),
            "toBlock": hex(end),
            "topics": [topic],
        }],
    )
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise AcquisitionError("eth_getLogs returned malformed result")
    for row in value:
        _validate_log_shape(row, topic=topic, start=start, end=end)
    return sorted(value, key=_event_key)


def _fetch_topic_range(
    rpc: qualification.RpcCall,
    *,
    topic: str,
    start: int,
    end: int,
    query_span: int,
    workers: int,
) -> tuple[list[Mapping[str, Any]], list[dict[str, int]]]:
    if query_span < 1:
        raise AcquisitionError("query span must be positive")
    if workers < 1 or workers > MAX_COVERAGE_WORKERS:
        raise AcquisitionError(
            f"coverage workers must be between 1 and {MAX_COVERAGE_WORKERS}"
        )

    chunks: list[tuple[int, int]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + query_span - 1)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + 1

    def fetch(bounds: tuple[int, int]) -> list[Mapping[str, Any]]:
        return _fetch_topic_chunk(
            rpc, topic=topic, start=bounds[0], end=bounds[1]
        )

    ordered_chunks: list[list[Mapping[str, Any]]] = []
    if workers == 1:
        ordered_chunks = [fetch(bounds) for bounds in chunks]
    else:
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="qntyspot-dev-acquisition-range",
        ) as executor:
            for offset in range(0, len(chunks), workers):
                batch = chunks[offset:offset + workers]
                futures = [executor.submit(fetch, bounds) for bounds in batch]
                ordered_chunks.extend(future.result() for future in futures)

    rows: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk_rows in ordered_chunks:
        for row in chunk_rows:
            identity = qualification._log_identity(row)
            if identity in seen:
                raise AcquisitionError("duplicate canonical log identity across DEV chunks")
            seen.add(identity)
            rows.append(row)
    rows.sort(key=_event_key)

    receipts = [
        {"from_block": chunk_start, "to_block": chunk_end}
        for chunk_start, chunk_end in chunks
    ]
    return rows, receipts


def _fetch_block_summaries(
    rpc: qualification.RpcCall,
    logs: list[Mapping[str, Any]],
    *,
    workers: int,
) -> dict[int, dict[str, Any]]:
    if workers < 1 or workers > MAX_BLOCK_WORKERS:
        raise AcquisitionError(
            f"block workers must be between 1 and {MAX_BLOCK_WORKERS}"
        )
    numbers = sorted({qualification._hex_int(row.get("blockNumber")) for row in logs})

    def fetch(number: int) -> tuple[int, dict[str, Any]]:
        block = qualification._block(rpc, number)
        return number, qualification._block_summary(block)

    summaries: dict[int, dict[str, Any]] = {}
    if workers == 1 or len(numbers) <= 1:
        for number in numbers:
            key, summary = fetch(number)
            summaries[key] = summary
    else:
        with ThreadPoolExecutor(
            max_workers=min(workers, len(numbers)),
            thread_name_prefix="qntyspot-dev-acquisition-block",
        ) as executor:
            for number, summary in executor.map(fetch, numbers):
                summaries[number] = summary

    for row in logs:
        number = qualification._hex_int(row.get("blockNumber"))
        row_hash = row.get("blockHash")
        if not isinstance(row_hash, str):
            raise AcquisitionError("historical log is missing blockHash")
        if row_hash.lower() != summaries[number]["hash"]:
            raise AcquisitionError(
                "STOP_SOURCE_CONFLICT: acquired log hash disagrees with canonical block metadata"
            )
    return summaries


def _decode_sync_reserves(log: Mapping[str, Any]) -> tuple[int, int]:
    data = log.get("data")
    if not isinstance(data, str) or not data.startswith("0x"):
        raise AcquisitionError("Sync log data is not hex")
    raw = data[2:]
    if len(raw) != 128:
        raise AcquisitionError("Sync log data must contain exactly two ABI words")
    try:
        reserve0 = int(raw[:64], 16)
        reserve1 = int(raw[64:], 16)
    except ValueError as exc:
        raise AcquisitionError("Sync log data is malformed") from exc
    max_uint112 = (1 << 112) - 1
    if reserve0 > max_uint112 or reserve1 > max_uint112:
        raise AcquisitionError("Sync reserve exceeds uint112")
    return reserve0, reserve1


def _sample_indices(count: int) -> list[int]:
    if count < 0:
        raise AcquisitionError("negative sample population")
    if count <= GAS_SAMPLE_MAX:
        return list(range(count))
    denominator = GAS_SAMPLE_MAX - 1
    return [
        (i * (count - 1)) // denominator
        for i in range(GAS_SAMPLE_MAX)
    ]


def _nearest_rank(values: list[int], percentile: int) -> int | None:
    if not values:
        return None
    if percentile < 1 or percentile > 100:
        raise AcquisitionError("percentile must be between 1 and 100")
    ordered = sorted(values)
    rank = math.ceil((percentile * len(ordered)) / 100) - 1
    return ordered[rank]


def _chronological_swap_transactions(
    swap_logs: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    values: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for log in sorted(swap_logs, key=_event_key):
        tx_hash = log.get("transactionHash")
        if not isinstance(tx_hash, str):
            raise AcquisitionError("Swap log missing transaction hash")
        key = tx_hash.lower()
        if key in seen:
            continue
        seen.add(key)
        values.append(log)
    return values


def _gas_evidence(
    rpc: qualification.RpcCall,
    swap_logs: list[Mapping[str, Any]],
    block_summaries: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    tx_logs = _chronological_swap_transactions(swap_logs)
    sample_indices = _sample_indices(len(tx_logs))
    samples: list[dict[str, Any]] = []

    for sample_index in sample_indices:
        log = tx_logs[sample_index]
        tx_hash = str(log["transactionHash"]).lower()
        log_block_number = qualification._hex_int(log["blockNumber"])
        log_block_hash = str(log["blockHash"]).lower()
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        if not isinstance(receipt, dict):
            raise AcquisitionError("selected DEV Swap receipt unavailable")
        if str(receipt.get("transactionHash", "")).lower() != tx_hash:
            raise AcquisitionError("selected DEV Swap receipt transaction mismatch")
        receipt_block_number = qualification._hex_int(receipt.get("blockNumber"))
        receipt_block_hash = str(receipt.get("blockHash", "")).lower()
        if receipt_block_number != log_block_number or receipt_block_hash != log_block_hash:
            raise AcquisitionError("selected DEV Swap receipt/log block mismatch")
        if block_summaries[log_block_number]["hash"] != receipt_block_hash:
            raise AcquisitionError("selected DEV Swap receipt is not canonical")
        if qualification._hex_int(receipt.get("status")) != 1:
            raise AcquisitionError("selected DEV Swap receipt is not successful")
        gas_used = qualification._hex_int(receipt.get("gasUsed"))
        effective_gas_price = qualification._hex_int(receipt.get("effectiveGasPrice"))
        gas_cost_wei = gas_used * effective_gas_price
        samples.append({
            "population_index": sample_index,
            "transaction_hash": tx_hash,
            "block_number": receipt_block_number,
            "block_hash": receipt_block_hash,
            "gas_used": gas_used,
            "effective_gas_price_wei": effective_gas_price,
            "gas_cost_wei": gas_cost_wei,
        })

    gas_costs = [row["gas_cost_wei"] for row in samples]
    return {
        "mode": (
            "DEV_DERIVED"
            if len(tx_logs) >= GAS_RECEIPT_THRESHOLD
            else "SENSITIVITY_FALLBACK"
        ),
        "receipt_threshold": GAS_RECEIPT_THRESHOLD,
        "swap_transaction_population_count": len(tx_logs),
        "sample_count": len(samples),
        "sample_indices": sample_indices,
        "samples": samples,
        "p50_gas_cost_wei": _nearest_rank(gas_costs, 50),
        "p90_gas_cost_wei": _nearest_rank(gas_costs, 90),
        "fallback_sensitivity_grid_weth": [
            "0", "0.000001", "0.00001", "0.0001", "0.001"
        ],
        "fallback_selection_gas_weth": "0.00001",
    }


def _serialize_jsonl(rows: list[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) + b"\n" for row in rows)


def _artifact_identity(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": _sha256_bytes(payload),
        "bytes": len(payload),
    }


def materialize_dev_package(
    rpc: qualification.RpcCall,
    *,
    primary_qualification: Mapping[str, Any],
    secondary_qualification: Mapping[str, Any],
    acquisition_provider_id: str,
    canonical_qntylab_source_sha: str,
    output_dir: Path,
    root: Path = Path("."),
    query_span: int = DEFAULT_QUERY_SPAN,
    coverage_workers: int = DEFAULT_COVERAGE_WORKERS,
    block_workers: int = DEFAULT_BLOCK_WORKERS,
) -> dict[str, Any]:
    _validate_qualification_pair(primary_qualification, secondary_qualification)
    if acquisition_provider_id not in {
        primary_qualification.get("provider_id"),
        secondary_qualification.get("provider_id"),
    }:
        raise AcquisitionError("acquisition provider must be one of the qualified providers")
    if not isinstance(canonical_qntylab_source_sha, str) or len(canonical_qntylab_source_sha) != 40:
        raise AcquisitionError("canonical QntyLab source SHA is invalid")

    t0_block = primary_qualification["t0_block"]["number"]
    dev_end_block = primary_qualification["dev_end_block"]["number"]
    t1 = primary_qualification["t1_block"]
    if not isinstance(t0_block, int) or not isinstance(dev_end_block, int):
        raise AcquisitionError("qualification block boundaries are malformed")
    if t0_block > dev_end_block:
        raise AcquisitionError("qualification DEV interval is inverted")

    sync_logs, sync_requests = _fetch_topic_range(
        rpc,
        topic=SYNC_TOPIC,
        start=t0_block,
        end=dev_end_block,
        query_span=query_span,
        workers=coverage_workers,
    )
    expected_coverage = primary_qualification["dev_log_coverage"]
    sync_identity_rows = [_event_identity(log) for log in sync_logs]
    if len(sync_identity_rows) != expected_coverage["sync_log_count"]:
        raise AcquisitionError("acquired Sync count disagrees with qualified DEV identity")
    if _digest(sync_identity_rows) != expected_coverage["sync_log_identity_digest"]:
        raise AcquisitionError("acquired Sync digest disagrees with qualified DEV identity")

    swap_logs, swap_requests = _fetch_topic_range(
        rpc,
        topic=SWAP_TOPIC,
        start=t0_block,
        end=dev_end_block,
        query_span=query_span,
        workers=coverage_workers,
    )
    all_logs = list(sync_logs) + list(swap_logs)
    block_summaries = _fetch_block_summaries(
        rpc, all_logs, workers=block_workers
    )

    reserve_rows: list[dict[str, Any]] = []
    for log in sync_logs:
        reserve0, reserve1 = _decode_sync_reserves(log)
        identity = _event_identity(log)
        block_number = identity["block_number"]
        reserve_rows.append({
            "chain_id": qualification.CHAIN_ID,
            "pool_address": qualification._norm_address(POOL),
            "block_number": block_number,
            "block_hash": identity["block_hash"],
            "transaction_hash": identity["transaction_hash"],
            "transaction_index": identity["transaction_index"],
            "log_index": identity["log_index"],
            "timestamp": block_summaries[block_number]["timestamp"],
            "event_or_source_type": "SYNC",
            "reserve0_atomic": reserve0,
            "reserve1_atomic": reserve1,
            "acquisition_source_provider_identity": acquisition_provider_id,
        })
    reserve_rows.sort(
        key=lambda row: (
            row["block_number"],
            row["transaction_index"],
            row["log_index"],
        )
    )

    gas = _gas_evidence(rpc, swap_logs, block_summaries)

    if output_dir.exists():
        raise AcquisitionError("immutable DEV output directory already exists")
    authorization_bytes = (root / AUTHORIZATION_PATH).read_bytes()
    historical_activation_bytes = (root / HISTORICAL_ACTIVATION_PATH).read_bytes()

    output_dir.mkdir(parents=True, exist_ok=False)
    reserve_path = output_dir / "dev_reserves.jsonl"
    gas_path = output_dir / "dev_gas_evidence.json"
    reserve_payload = _serialize_jsonl(reserve_rows)
    gas_payload = _canonical_bytes(gas) + b"\n"
    reserve_path.write_bytes(reserve_payload)
    gas_path.write_bytes(gas_payload)

    primary_material_digest = _digest(
        qualification.material_identity(primary_qualification)
    )
    secondary_material_digest = _digest(
        qualification.material_identity(secondary_qualification)
    )

    timestamps = [row["timestamp"] for row in reserve_rows]
    blocks = [row["block_number"] for row in reserve_rows]
    dataset_artifacts = {
        "dev_reserves": _artifact_identity(reserve_path, reserve_payload),
        "dev_gas_evidence": _artifact_identity(gas_path, gas_payload),
    }
    manifest_core = {
        "artifact_type": "QNTYSPOT_INK_DEV_ACQUISITION_MANIFEST_V1",
        "acquisition_project_id": PROJECT_ID,
        "canonical_qntylab_source_sha": canonical_qntylab_source_sha,
        "governing_activation_identity": {
            "active_authorization_path": str(AUTHORIZATION_PATH),
            "active_authorization_sha256": _sha256_bytes(authorization_bytes),
            "historical_activation_path": str(HISTORICAL_ACTIVATION_PATH),
            "historical_activation_sha256": _sha256_bytes(historical_activation_bytes),
            "historical_activation_is_template_only": True,
        },
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "qntyspot_source_sha": QNTYSPOT_SOURCE_SHA,
        "chain_id": qualification.CHAIN_ID,
        "pool_address": qualification._norm_address(POOL),
        "t0": primary_qualification["t0_block"],
        "dev_end": primary_qualification["dev_end_block"],
        "t1": t1,
        "source_identities": [
            {
                "provider_id": primary_qualification["provider_id"],
                "material_identity_digest": primary_material_digest,
                "qualification_receipt_digest": primary_qualification.get("receipt_digest"),
            },
            {
                "provider_id": secondary_qualification["provider_id"],
                "material_identity_digest": secondary_material_digest,
                "qualification_receipt_digest": secondary_qualification.get("receipt_digest"),
            },
        ],
        "acquisition_provider_id": acquisition_provider_id,
        "request_and_range_receipts": {
            "sync": {
                "topic": SYNC_TOPIC,
                "query_span_blocks": query_span,
                "requests": sync_requests,
            },
            "swap": {
                "topic": SWAP_TOPIC,
                "query_span_blocks": query_span,
                "requests": swap_requests,
            },
        },
        "row_or_event_counts": {
            "sync_reserve_rows": len(reserve_rows),
            "swap_logs_for_gas_population": len(
                _chronological_swap_transactions(swap_logs)
            ),
            "gas_samples": gas["sample_count"],
        },
        "min_max_block": {
            "min": min(blocks) if blocks else None,
            "max": max(blocks) if blocks else None,
        },
        "min_max_timestamp": {
            "min": min(timestamps) if timestamps else None,
            "max": max(timestamps) if timestamps else None,
        },
        "duplicate_count": 0,
        "discarded_outer_overfetch_count": 0,
        "integrity_checks": [
            "TWO_DISTINCT_QUALIFIED_PROVIDERS_MATCH_EXACT_MATERIAL_IDENTITY",
            "ALL_ECONOMIC_REQUESTS_HARD_CAPPED_AT_DEV_END",
            "ACQUIRED_SYNC_COUNT_MATCHES_QUALIFICATION",
            "ACQUIRED_SYNC_IDENTITY_DIGEST_MATCHES_QUALIFICATION",
            "ALL_ACQUIRED_LOGS_BOUND_TO_CANONICAL_BLOCK_METADATA",
            "RESERVES_STORED_AS_INTEGER_ATOMIC_UNITS",
            "DETERMINISTIC_BLOCK_TX_LOG_ORDER",
            "GAS_SAMPLE_RULE_FROZEN",
            "NO_CANDIDATE_EVALUATION",
            "NO_OUTER_ACCESS",
        ],
        "sha256_per_dataset_artifact": dataset_artifacts,
        "performance_metrics_allowed": False,
        "candidate_evaluation_performed": False,
        "outer_access_performed": False,
        "outer_evaluation_count": 0,
    }
    manifest = dict(manifest_core)
    manifest["package_digest"] = _digest(manifest_core)
    manifest_path = output_dir / "dev_manifest.json"
    manifest_payload = json.dumps(
        manifest, sort_keys=True, indent=2, ensure_ascii=True
    ).encode("utf-8") + b"\n"
    manifest_path.write_bytes(manifest_payload)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize immutable QntySpot Ink DEV evidence only"
    )
    parser.add_argument("--primary-qualification", required=True)
    parser.add_argument("--secondary-qualification", required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--query-span", type=int, default=DEFAULT_QUERY_SPAN)
    parser.add_argument(
        "--coverage-workers", type=int, default=DEFAULT_COVERAGE_WORKERS
    )
    parser.add_argument(
        "--block-workers", type=int, default=DEFAULT_BLOCK_WORKERS
    )
    args = parser.parse_args(argv)

    root = Path(".").resolve()
    qualification.assert_canonical_stage_b_authority(root)

    primary = _load_json(Path(args.primary_qualification))
    secondary = _load_json(Path(args.secondary_qualification))
    _validate_qualification_pair(primary, secondary)

    endpoint = os.environ.get("QNTYSPOT_INK_RPC_URL")
    if not endpoint:
        raise AcquisitionError("QNTYSPOT_INK_RPC_URL is required")
    canonical_sha = qualification._git(root, "rev-parse", "HEAD")
    materialize_dev_package(
        qualification.JsonRpcClient(endpoint).call,
        primary_qualification=primary,
        secondary_qualification=secondary,
        acquisition_provider_id=args.provider_id,
        canonical_qntylab_source_sha=canonical_sha,
        output_dir=Path(args.output_dir),
        root=root,
        query_span=args.query_span,
        coverage_workers=args.coverage_workers,
        block_workers=args.block_workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
