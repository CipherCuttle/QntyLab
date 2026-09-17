"""Outcome-blind source qualification for QntySpot Ink Stage B.

This module proves that a JSON-RPC source can faithfully serve the frozen
Ink/pool identity and DEV-bounded historical evidence without opening OUTER.
T1 is inspected only through block metadata. Economic Sync-log requests begin
at outcome-blind T0 discovery and are never deliberately issued past DEV_END.

Real network execution is fail-closed unless the checkout is canonical master
and the Stage-B ACTIVE_RESEARCH registry row is present. Importing this module
never performs network I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping


PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_RESEARCH_V1"
PREDECESSOR_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_RESEARCH_V1"
CHAIN_ID = 57073
KRAKMASK = "0x32bcb803f696c99eb263d60a05cafd8689026575"
WETH9 = "0x4200000000000000000000000000000000000006"
FACTORY = "0x458c5d5b75ccba22651d2c5b61cb1ea1e0b0f95d"
POOL = "0xed11ed4b195e84ba9b74c4d6ce13b7a43b354264"
CUTOFF_UTC = "2026-08-25T17:02:37Z"
SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"
FACTORY_SELECTOR = "0xc45a0155"
DEFAULT_PROBE_SPAN = 256
MAX_T0_SCAN_BLOCKS = 8192
MIN_TOTAL_HISTORY_SECONDS = 30 * 24 * 60 * 60
MIN_DEV_HISTORY_SECONDS = 18 * 24 * 60 * 60
MIN_OUTER_HISTORY_SECONDS = 12 * 24 * 60 * 60


class QualificationError(RuntimeError):
    """Fail-closed source qualification error."""


RpcCall = Callable[[str, list[Any]], Any]


def _norm_address(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 42:
        raise QualificationError(f"invalid address: {value!r}")
    return value.lower()


def _hex_int(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise QualificationError(f"invalid JSON-RPC integer: {value!r}")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise QualificationError(f"invalid JSON-RPC integer: {value!r}") from exc


def _decode_address_word(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise QualificationError("eth_call returned a non-hex result")
    raw = value[2:]
    if len(raw) < 40:
        raise QualificationError("eth_call address result is too short")
    return _norm_address("0x" + raw[-40:])


def _cutoff_timestamp() -> int:
    return int(datetime.fromisoformat(CUTOFF_UTC.replace("Z", "+00:00")).timestamp())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _has_code(value: Any) -> bool:
    return isinstance(value, str) and value not in {"0x", "0x0", "0x00"}


@dataclass
class JsonRpcClient:
    endpoint: str
    timeout_seconds: float = 20.0
    request_id: int = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        payload = _canonical_bytes({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        })
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QualificationError(f"JSON-RPC transport failure for {method}: {type(exc).__name__}") from exc
        if not isinstance(body, dict) or body.get("id") != self.request_id:
            raise QualificationError(f"malformed JSON-RPC response for {method}")
        if body.get("error") is not None:
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise QualificationError(f"JSON-RPC error for {method}: code={code}")
        if "result" not in body:
            raise QualificationError(f"JSON-RPC result missing for {method}")
        return body["result"]


def _block(rpc: RpcCall, number: int) -> Mapping[str, Any]:
    result = rpc("eth_getBlockByNumber", [hex(number), False])
    if not isinstance(result, dict):
        raise QualificationError(f"historical block unavailable: {number}")
    if _hex_int(result.get("number")) != number:
        raise QualificationError(f"historical block number mismatch: {number}")
    if not isinstance(result.get("hash"), str) or not isinstance(result.get("timestamp"), str):
        raise QualificationError(f"historical block identity incomplete: {number}")
    return result


def _block_summary(block: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "number": _hex_int(block["number"]),
        "hash": block["hash"].lower(),
        "timestamp": _hex_int(block["timestamp"]),
    }


def find_block_at_or_before_timestamp(rpc: RpcCall, timestamp: int) -> Mapping[str, Any]:
    latest_number = _hex_int(rpc("eth_blockNumber", []))
    latest = _block(rpc, latest_number)
    if _hex_int(latest["timestamp"]) < timestamp:
        raise QualificationError("provider latest block predates requested historical timestamp")

    low, high = 0, latest_number
    best: Mapping[str, Any] | None = None
    while low <= high:
        mid = (low + high) // 2
        current = _block(rpc, mid)
        current_ts = _hex_int(current["timestamp"])
        if current_ts <= timestamp:
            best = current
            low = mid + 1
        else:
            high = mid - 1
    if best is None:
        raise QualificationError("no canonical block exists at or before requested timestamp")
    return best


def find_first_code_block(rpc: RpcCall, address: str, end_block: int) -> int:
    """Find first historical block with bytecode using only non-economic metadata."""
    if end_block < 0:
        raise QualificationError("invalid historical code-search boundary")
    if not _has_code(rpc("eth_getCode", [address, hex(end_block)])):
        raise QualificationError("STOP_SOURCE_CONFLICT: pool bytecode absent at frozen T1")

    low, high = 0, end_block
    while low < high:
        mid = (low + high) // 2
        if _has_code(rpc("eth_getCode", [address, hex(mid)])):
            high = mid
        else:
            low = mid + 1
    first = low
    if not _has_code(rpc("eth_getCode", [address, hex(first)])):
        raise QualificationError("STOP_SOURCE_CONFLICT: historical pool deployment boundary is unstable")
    if first > 0 and _has_code(rpc("eth_getCode", [address, hex(first - 1)])):
        raise QualificationError("STOP_SOURCE_CONFLICT: historical pool deployment boundary is non-monotonic")
    return first


def _pool_call(rpc: RpcCall, selector: str) -> str:
    return _decode_address_word(rpc("eth_call", [{"to": POOL, "data": selector}, "latest"]))


def _log_identity(log: Mapping[str, Any]) -> tuple[str, str, str]:
    block_hash = log.get("blockHash")
    tx_hash = log.get("transactionHash")
    log_index = log.get("logIndex")
    if not all(isinstance(item, str) for item in (block_hash, tx_hash, log_index)):
        raise QualificationError("historical log is missing canonical identity")
    if log.get("removed") is True:
        raise QualificationError("historical probe returned a removed log")
    _hex_int(log_index)
    return block_hash.lower(), tx_hash.lower(), log_index.lower()


def _log_order_key(log: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        _hex_int(log.get("blockNumber")),
        _hex_int(log.get("transactionIndex")),
        _hex_int(log.get("logIndex")),
    )


def _event_identity(log: Mapping[str, Any]) -> dict[str, Any]:
    block_hash, tx_hash, _ = _log_identity(log)
    block_number, transaction_index, log_index = _log_order_key(log)
    return {
        "block_number": block_number,
        "transaction_index": transaction_index,
        "log_index": log_index,
        "block_hash": block_hash,
        "transaction_hash": tx_hash,
    }



def _sync_logs(
    rpc: RpcCall,
    start: int,
    end: int,
    canonical_block_hashes: dict[int, str] | None = None,
) -> list[Mapping[str, Any]]:
    if start > end:
        return []
    result = rpc("eth_getLogs", [{
        "address": POOL,
        "fromBlock": hex(start),
        "toBlock": hex(end),
        "topics": [SYNC_TOPIC],
    }])
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise QualificationError("eth_getLogs returned malformed result")

    cache = canonical_block_hashes if canonical_block_hashes is not None else {}
    for row in result:
        if _norm_address(row.get("address")) != _norm_address(POOL):
            raise QualificationError("STOP_SOURCE_CONFLICT: provider returned a log for the wrong address")
        topics = row.get("topics")
        if not isinstance(topics, list) or not topics or not isinstance(topics[0], str) or topics[0].lower() != SYNC_TOPIC:
            raise QualificationError("STOP_SOURCE_CONFLICT: provider returned a non-Sync log")
        block_number = _hex_int(row.get("blockNumber"))
        if not start <= block_number <= end:
            raise QualificationError("STOP_SOURCE_CONFLICT: provider over-returned a log outside the requested range")
        canonical_hash = cache.get(block_number)
        if canonical_hash is None:
            canonical_hash = str(_block(rpc, block_number)["hash"]).lower()
            cache[block_number] = canonical_hash
        row_hash = row.get("blockHash")
        if not isinstance(row_hash, str) or row_hash.lower() != canonical_hash:
            raise QualificationError("STOP_SOURCE_CONFLICT: log block hash disagrees with canonical block metadata")
        _log_order_key(row)
        _log_identity(row)
    return result

def _identities(logs: list[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    values = [_log_identity(log) for log in logs]
    if len(values) != len(set(values)):
        raise QualificationError("duplicate canonical log identity in provider response")
    return values



def find_t0_sync(
    rpc: RpcCall,
    deployment_block: int,
    t1_block: int,
    *,
    max_scan_blocks: int = MAX_T0_SCAN_BLOCKS,
    canonical_block_hashes: dict[int, str] | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Find T0 with singleton Sync queries so no future interval is pre-opened."""
    if max_scan_blocks < 1:
        raise QualificationError("T0 scan limit must be positive")
    last = min(t1_block, deployment_block + max_scan_blocks - 1)
    for number in range(deployment_block, last + 1):
        logs = _sync_logs(rpc, number, number, canonical_block_hashes)
        if logs:
            first = min(logs, key=_log_order_key)
            block = _block(rpc, number)
            if _log_identity(first)[0] != str(block["hash"]).lower():
                raise QualificationError("STOP_SOURCE_CONFLICT: T0 Sync is not bound to canonical block metadata")
            return block, first
    raise QualificationError(
        "STOP_SOURCE_CONFLICT: no eligible Sync observation found within outcome-blind T0 scan bound"
    )

def _dev_end_timestamp(t0_timestamp: int) -> int:
    t1_timestamp = _cutoff_timestamp()
    if t0_timestamp >= t1_timestamp:
        raise QualificationError("STOP_SOURCE_CONFLICT: T0 does not precede frozen T1")
    return t0_timestamp + ((t1_timestamp - t0_timestamp) * 3) // 5


def _validate_history_window(t0_timestamp: int, dev_end_timestamp: int) -> dict[str, int]:
    t1_timestamp = _cutoff_timestamp()
    total = t1_timestamp - t0_timestamp
    dev = dev_end_timestamp - t0_timestamp
    outer = t1_timestamp - dev_end_timestamp
    if (
        total < MIN_TOTAL_HISTORY_SECONDS
        or dev < MIN_DEV_HISTORY_SECONDS
        or outer < MIN_OUTER_HISTORY_SECONDS
    ):
        raise QualificationError(
            "INSUFFICIENT_HISTORY: frozen 30-day total / 18-day DEV / 12-day OUTER minimum is not met"
        )
    return {
        "total": total,
        "dev": dev,
        "outer": outer,
    }



def _bounded_log_integrity_probe(
    rpc: RpcCall,
    t0_block: int,
    dev_end_block: int,
    span: int,
    canonical_block_hashes: dict[int, str] | None = None,
) -> dict[str, Any]:
    if span < 2:
        raise QualificationError("qualification probe span must be >= 2")
    start = t0_block
    end = min(dev_end_block, t0_block + span - 1)
    if end <= start:
        raise QualificationError("STOP_SOURCE_CONFLICT: DEV interval is too short for split-range integrity probe")
    midpoint = (start + end) // 2

    whole_a = _sync_logs(rpc, start, end, canonical_block_hashes)
    whole_b = _sync_logs(rpc, start, end, canonical_block_hashes)
    ordered_a = sorted(whole_a, key=_log_order_key)
    ordered_b = sorted(whole_b, key=_log_order_key)
    whole_ids_a = _identities(ordered_a)
    whole_ids_b = _identities(ordered_b)
    if whole_ids_a != whole_ids_b:
        raise QualificationError("STOP_SOURCE_CONFLICT: repeated historical log request is nondeterministic")

    left = sorted(_sync_logs(rpc, start, midpoint, canonical_block_hashes), key=_log_order_key)
    right = sorted(_sync_logs(rpc, midpoint + 1, end, canonical_block_hashes), key=_log_order_key)
    left_ids = _identities(left)
    right_ids = _identities(right)
    combined = sorted(left_ids + right_ids)
    if sorted(whole_ids_a) != combined:
        raise QualificationError("STOP_SOURCE_CONFLICT: whole-range logs disagree with split-range logs")
    if not ordered_a:
        raise QualificationError("STOP_SOURCE_CONFLICT: no Sync log available in DEV-bounded receipt probe")

    first = ordered_a[0]
    first_id = _log_identity(first)
    receipt = rpc("eth_getTransactionReceipt", [first_id[1]])
    if not isinstance(receipt, dict):
        raise QualificationError("STOP_SOURCE_CONFLICT: historical transaction receipt unavailable")
    receipt_tx_hash = receipt.get("transactionHash")
    receipt_block_hash = receipt.get("blockHash")
    receipt_block_number = _hex_int(receipt.get("blockNumber"))
    if not isinstance(receipt_tx_hash, str) or receipt_tx_hash.lower() != first_id[1]:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt transaction hash disagrees with probed log")
    if not isinstance(receipt_block_hash, str) or receipt_block_hash.lower() != first_id[0]:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt/log canonical block disagreement")
    if not start <= receipt_block_number <= end:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt escaped DEV-bounded probe range")
    canonical_receipt_hash = str(_block(rpc, receipt_block_number)["hash"]).lower()
    if receipt_block_hash.lower() != canonical_receipt_hash:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt block hash disagrees with canonical block metadata")
    if _hex_int(receipt.get("status")) != 1:
        raise QualificationError("STOP_SOURCE_CONFLICT: probed Sync receipt is not successful")
    gas_used = receipt.get("gasUsed")
    if not isinstance(gas_used, str):
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt gasUsed is missing or invalid")
    if _hex_int(gas_used) <= 0:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt gasUsed is missing or invalid")
    effective_gas_price = receipt.get("effectiveGasPrice")
    if not isinstance(effective_gas_price, str):
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt effectiveGasPrice is missing or invalid")
    _hex_int(effective_gas_price)

    event_records = [_event_identity(log) for log in ordered_a]
    return {
        "from_block": start,
        "to_block": end,
        "span_blocks": end - start + 1,
        "sync_log_count": len(event_records),
        "sync_log_identity_digest": _digest(event_records),
        "receipt_probe_transaction_hash": first_id[1],
        "receipt_probe_block_hash": first_id[0],
    }

def _dev_log_coverage(
    rpc: RpcCall,
    start: int,
    end: int,
    query_span: int,
    canonical_block_hashes: dict[int, str] | None = None,
) -> dict[str, Any]:
    if query_span < 2:
        raise QualificationError("qualification query span must be >= 2")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    chunk_count = 0
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + query_span - 1)
        logs = sorted(
            _sync_logs(rpc, cursor, chunk_end, canonical_block_hashes),
            key=_log_order_key,
        )
        for log in logs:
            identity = _log_identity(log)
            if identity in seen:
                raise QualificationError("STOP_SOURCE_CONFLICT: duplicate canonical log identity across DEV chunks")
            seen.add(identity)
            records.append(_event_identity(log))
        chunk_count += 1
        cursor = chunk_end + 1
    return {
        "from_block": start,
        "to_block": end,
        "query_span_blocks": query_span,
        "chunk_count": chunk_count,
        "sync_log_count": len(records),
        "sync_log_identity_digest": _digest(records),
        "canonical_block_binding_verified": True,
    }



def qualify_source(rpc: RpcCall, *, provider_id: str, probe_span: int = DEFAULT_PROBE_SPAN) -> dict[str, Any]:
    if not provider_id or any(token in provider_id.lower() for token in ("http://", "https://", "?key=", "apikey")):
        raise QualificationError("provider_id must be a non-secret label, never an endpoint URL")
    if probe_span < 2:
        raise QualificationError("qualification probe span must be >= 2")

    chain_id = _hex_int(rpc("eth_chainId", []))
    if chain_id != CHAIN_ID:
        raise QualificationError(f"STOP_SOURCE_CONFLICT: chain ID {chain_id} != {CHAIN_ID}")

    for label, address in (("pool", POOL), ("factory", FACTORY)):
        code = rpc("eth_getCode", [address, "latest"])
        if not _has_code(code):
            raise QualificationError(f"STOP_SOURCE_CONFLICT: {label} bytecode unavailable")

    token0 = _pool_call(rpc, TOKEN0_SELECTOR)
    token1 = _pool_call(rpc, TOKEN1_SELECTOR)
    if {token0, token1} != {_norm_address(KRAKMASK), _norm_address(WETH9)}:
        raise QualificationError("STOP_SOURCE_CONFLICT: pool token identity mismatch")
    pool_factory = _pool_call(rpc, FACTORY_SELECTOR)
    if pool_factory != _norm_address(FACTORY):
        raise QualificationError("STOP_SOURCE_CONFLICT: pool factory mismatch")

    t1 = find_block_at_or_before_timestamp(rpc, _cutoff_timestamp())
    t1_number = _hex_int(t1["number"])
    t1_timestamp = _hex_int(t1["timestamp"])
    if t1_timestamp > _cutoff_timestamp():
        raise QualificationError("STOP_SOURCE_CONFLICT: T1 block search crossed the frozen cutoff")

    canonical_block_hashes: dict[int, str] = {t1_number: str(t1["hash"]).lower()}
    deployment_block = find_first_code_block(rpc, POOL, t1_number)
    t0, t0_log = find_t0_sync(
        rpc,
        deployment_block,
        t1_number,
        canonical_block_hashes=canonical_block_hashes,
    )
    t0_number = _hex_int(t0["number"])
    t0_timestamp = _hex_int(t0["timestamp"])
    if _hex_int(t0_log["blockNumber"]) != t0_number:
        raise QualificationError("STOP_SOURCE_CONFLICT: T0 Sync/block disagreement")

    dev_end_timestamp = _dev_end_timestamp(t0_timestamp)
    history_seconds = _validate_history_window(t0_timestamp, dev_end_timestamp)
    dev_end = find_block_at_or_before_timestamp(rpc, dev_end_timestamp)
    dev_end_number = _hex_int(dev_end["number"])
    if dev_end_number < t0_number or _hex_int(dev_end["timestamp"]) > dev_end_timestamp:
        raise QualificationError("STOP_SOURCE_CONFLICT: mechanical DEV_END block is invalid")
    canonical_block_hashes[dev_end_number] = str(dev_end["hash"]).lower()

    probe = _bounded_log_integrity_probe(
        rpc,
        t0_number,
        dev_end_number,
        probe_span,
        canonical_block_hashes,
    )
    if probe["to_block"] > dev_end_number:
        raise QualificationError("STOP_SOURCE_CONFLICT: economic probe crossed DEV_END")

    coverage = _dev_log_coverage(
        rpc,
        t0_number,
        dev_end_number,
        probe_span,
        canonical_block_hashes,
    )
    if coverage["to_block"] != dev_end_number or coverage["from_block"] != t0_number:
        raise QualificationError("STOP_SOURCE_CONFLICT: DEV coverage did not span the full required range")
    if coverage["sync_log_count"] < 1:
        raise QualificationError("STOP_SOURCE_CONFLICT: DEV coverage contains no Sync observations")

    checks = [
        "CHAIN_ID_EXACT",
        "POOL_BYTECODE_PRESENT",
        "FACTORY_BYTECODE_PRESENT",
        "POOL_TOKEN_IDENTITY_EXACT",
        "POOL_FACTORY_EXACT",
        "T1_METADATA_RETRIEVABLE_WITHOUT_ECONOMIC_OUTER_REQUEST",
        "POOL_DEPLOYMENT_BOUNDARY_RETRIEVABLE",
        "T0_ESTABLISHED_OUTCOME_BLIND_BY_SINGLETON_SYNC_SCAN",
        "FROZEN_MINIMUM_HISTORY_30_18_12_DAYS",
        "DEV_END_COMPUTED_MECHANICALLY_BEFORE_MULTI_BLOCK_ECONOMIC_PROBE",
        "ECONOMIC_REQUESTS_HARD_CAPPED_AT_DEV_END",
        "EVERY_RETURNED_SYNC_BOUND_TO_CANONICAL_BLOCK_HASH",
        "BOUNDED_DEV_SYNC_LOG_RETRIEVAL",
        "REPEATED_REQUEST_DETERMINISTIC",
        "WHOLE_EQUALS_SPLIT_RANGE",
        "FULL_DEV_LOG_RANGE_COVERED_IN_BOUNDED_CHUNKS",
        "DEV_RECEIPT_TRANSACTION_AND_BLOCK_IDENTITY_BOUND",
        "RAW_SYNC_ECONOMIC_DATA_NOT_DECODED_OR_SERIALIZED",
    ]
    return {
        "artifact_type": "QNTYSPOT_INK_SOURCE_QUALIFICATION_RECEIPT_V1",
        "project_id": PROJECT_ID,
        "status": "PASS",
        "provider_id": provider_id,
        "provider_endpoint_serialized": False,
        "outcome_blind": True,
        "chain_id": chain_id,
        "pool": _norm_address(POOL),
        "factory": pool_factory,
        "token0": token0,
        "token1": token1,
        "frozen_cutoff_utc": CUTOFF_UTC,
        "t1_block": _block_summary(t1),
        "pool_deployment_block": deployment_block,
        "t0_block": _block_summary(t0),
        "t0_sync_identity": _event_identity(t0_log),
        "dev_end_timestamp": dev_end_timestamp,
        "dev_end_block": _block_summary(dev_end),
        "history_seconds": history_seconds,
        "bounded_probe": probe,
        "dev_log_coverage": coverage,
        "checks": checks,
        "raw_log_data_decoded": False,
        "raw_log_data_serialized": False,
        "outer_request_count": 0,
        "candidate_evaluation_performed": False,
        "outer_access_performed": False,
    }


def material_identity(receipt: Mapping[str, Any]) -> dict[str, Any]:
    probe = receipt["bounded_probe"]
    coverage = receipt["dev_log_coverage"]
    return {
        "chain_id": receipt["chain_id"],
        "pool": receipt["pool"],
        "factory": receipt["factory"],
        "tokens": sorted((receipt["token0"], receipt["token1"])),
        "t1_block": receipt["t1_block"],
        "pool_deployment_block": receipt["pool_deployment_block"],
        "t0_block": receipt["t0_block"],
        "t0_sync_identity": receipt["t0_sync_identity"],
        "dev_end_timestamp": receipt["dev_end_timestamp"],
        "dev_end_block": receipt["dev_end_block"],
        "history_seconds": receipt["history_seconds"],
        "bounded_probe_identity_digest": probe["sync_log_identity_digest"],
        "receipt_probe_transaction_hash": probe["receipt_probe_transaction_hash"],
        "receipt_probe_block_hash": probe["receipt_probe_block_hash"],
        "dev_log_coverage_identity_digest": coverage["sync_log_identity_digest"],
        "dev_log_coverage_count": coverage["sync_log_count"],
    }

def compare_sources(primary: Mapping[str, Any], secondary: Mapping[str, Any]) -> None:
    if material_identity(primary) != material_identity(secondary):
        raise QualificationError("STOP_SOURCE_CONFLICT: material cross-provider identity disagreement")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _git_fetch_origin_master(root: Path) -> None:
    result = subprocess.run(
        ["git", "fetch", "--quiet", "origin", "master"],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise QualificationError("canonical authority check could not refresh origin/master")


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0




def assert_canonical_stage_b_authority(root: Path = Path(".")) -> None:
    branch = _git(root, "branch", "--show-current")
    if branch != "master":
        raise QualificationError("real source qualification is forbidden outside canonical master")
    if _git(root, "status", "--porcelain"):
        raise QualificationError("real source qualification requires a clean canonical worktree")

    _git_fetch_origin_master(root)
    try:
        head = _git(root, "rev-parse", "HEAD")
        origin_master = _git(root, "rev-parse", "origin/master")
    except subprocess.CalledProcessError as exc:
        raise QualificationError("canonical authority check could not resolve HEAD/origin/master") from exc
    if head != origin_master:
        raise QualificationError("STOP_SOURCE_CONFLICT: local master is not exact refreshed origin/master")

    registry = tomllib.loads((root / "docs/state/projects.toml").read_text(encoding="utf-8"))["project"]
    rows = {row["project_id"]: row for row in registry}
    current = rows.get(PROJECT_ID)
    predecessor = rows.get(PREDECESSOR_ID)
    if not current or current.get("state") != "ACTIVE_RESEARCH" or current.get("implementation_authorized") is not True:
        raise QualificationError("canonical Stage-B ACTIVE_RESEARCH authority is absent")
    if not predecessor or predecessor.get("state") != "CLOSED_PASS" or predecessor.get("implementation_authorized") is not False:
        raise QualificationError("Stage-A predecessor is not closed before Stage-B network authority")

    required_base = current.get("required_base_sha")
    if not isinstance(required_base, str) or not _git_is_ancestor(root, required_base, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: Stage-B required canonical base is not an ancestor of HEAD")
    reviewed_candidate = current.get("reviewed_candidate_sha")
    if not isinstance(reviewed_candidate, str) or len(reviewed_candidate) != 40:
        raise QualificationError("STOP_SOURCE_CONFLICT: exact reviewed Stage-B candidate is not pinned")
    if not _git_is_ancestor(root, reviewed_candidate, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: exact reviewed Stage-B candidate is not canonical")

def _write_receipt(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(value)
    payload["receipt_digest"] = _digest(value)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Outcome-blind QntySpot Ink source qualification")
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--secondary-provider-id")
    parser.add_argument("--probe-span", type=int, default=DEFAULT_PROBE_SPAN)
    parser.add_argument(
        "--output",
        default="experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/source_qualification_receipt.json",
    )
    args = parser.parse_args(argv)

    root = Path(".").resolve()
    # This check intentionally occurs before reading endpoint environment
    # variables or constructing a transport, so a PR branch cannot make a
    # market-network request by invoking the CLI.
    assert_canonical_stage_b_authority(root)

    endpoint = os.environ.get("QNTYSPOT_INK_RPC_URL")
    if not endpoint:
        raise QualificationError("QNTYSPOT_INK_RPC_URL is required")
    primary = qualify_source(JsonRpcClient(endpoint).call, provider_id=args.provider_id, probe_span=args.probe_span)

    secondary_endpoint = os.environ.get("QNTYSPOT_INK_RPC_URL_SECONDARY")
    secondary: dict[str, Any] | None = None
    if secondary_endpoint:
        if not args.secondary_provider_id:
            raise QualificationError("--secondary-provider-id is required when a secondary endpoint is configured")
        secondary = qualify_source(
            JsonRpcClient(secondary_endpoint).call,
            provider_id=args.secondary_provider_id,
            probe_span=args.probe_span,
        )
        compare_sources(primary, secondary)

    receipt = dict(primary)
    receipt["secondary_provider_checked"] = secondary is not None
    if secondary is not None:
        receipt["secondary_provider_id"] = secondary["provider_id"]
        receipt["secondary_material_identity_digest"] = _digest(material_identity(secondary))
    _write_receipt(root / args.output, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
