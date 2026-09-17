"""Outcome-blind source qualification for QntySpot Ink Stage B.

This module is deliberately narrower than DEV acquisition.  It proves that a
JSON-RPC source can faithfully serve the frozen Ink/pool identity and a bounded
historical log/receipt probe without decoding or persisting economic log data.

Real network execution is fail-closed unless the checkout is canonical master
and the Stage-B ACTIVE_RESEARCH registry row is present.  Importing this module
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
from datetime import datetime, timezone
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
    return int(value, 16)


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


def find_block_at_or_before_timestamp(rpc: RpcCall, timestamp: int) -> Mapping[str, Any]:
    latest_number = _hex_int(rpc("eth_blockNumber", []))
    latest = _block(rpc, latest_number)
    if _hex_int(latest["timestamp"]) < timestamp:
        raise QualificationError("provider latest block predates frozen T1")

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
        raise QualificationError("no canonical block exists at or before frozen T1")
    return best


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
    return block_hash.lower(), tx_hash.lower(), log_index.lower()


def _sync_logs(rpc: RpcCall, start: int, end: int) -> list[Mapping[str, Any]]:
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
    return result


def _identities(logs: list[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    values = [_log_identity(log) for log in logs]
    if len(values) != len(set(values)):
        raise QualificationError("duplicate canonical log identity in provider response")
    return values


def _bounded_log_integrity_probe(rpc: RpcCall, t1_block: int, span: int) -> dict[str, Any]:
    if span < 2:
        raise QualificationError("qualification probe span must be >= 2")
    start = max(0, t1_block - span + 1)
    end = t1_block
    midpoint = (start + end) // 2

    whole_a = _sync_logs(rpc, start, end)
    whole_b = _sync_logs(rpc, start, end)
    whole_ids_a = _identities(whole_a)
    whole_ids_b = _identities(whole_b)
    if whole_ids_a != whole_ids_b:
        raise QualificationError("STOP_SOURCE_CONFLICT: repeated historical log request is nondeterministic")

    left_ids = _identities(_sync_logs(rpc, start, midpoint))
    right_ids = _identities(_sync_logs(rpc, midpoint + 1, end))
    combined = sorted(left_ids + right_ids)
    if sorted(whole_ids_a) != combined:
        raise QualificationError("STOP_SOURCE_CONFLICT: whole-range logs disagree with split-range logs")
    if not whole_a:
        raise QualificationError("STOP_SOURCE_CONFLICT: no Sync log available in bounded receipt probe")

    first = whole_a[0]
    first_id = _log_identity(first)
    receipt = rpc("eth_getTransactionReceipt", [first_id[1]])
    if not isinstance(receipt, dict):
        raise QualificationError("STOP_SOURCE_CONFLICT: historical transaction receipt unavailable")
    receipt_block_hash = receipt.get("blockHash")
    if not isinstance(receipt_block_hash, str) or receipt_block_hash.lower() != first_id[0]:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt/log canonical block disagreement")

    # Deliberately retain identities/counts only.  The raw Sync `data` field
    # contains reserve values and is neither decoded nor serialized here.
    return {
        "from_block": start,
        "to_block": end,
        "span_blocks": end - start + 1,
        "sync_log_count": len(whole_ids_a),
        "sync_log_identity_digest": _digest(whole_ids_a),
        "receipt_probe_transaction_hash": first_id[1],
        "receipt_probe_block_hash": first_id[0],
    }


def qualify_source(rpc: RpcCall, *, provider_id: str, probe_span: int = DEFAULT_PROBE_SPAN) -> dict[str, Any]:
    if not provider_id or any(token in provider_id.lower() for token in ("http://", "https://", "?key=", "apikey")):
        raise QualificationError("provider_id must be a non-secret label, never an endpoint URL")

    chain_id = _hex_int(rpc("eth_chainId", []))
    if chain_id != CHAIN_ID:
        raise QualificationError(f"STOP_SOURCE_CONFLICT: chain ID {chain_id} != {CHAIN_ID}")

    for label, address in (("pool", POOL), ("factory", FACTORY)):
        code = rpc("eth_getCode", [address, "latest"])
        if not isinstance(code, str) or code in {"0x", "0x0", "0x00"}:
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

    probe = _bounded_log_integrity_probe(rpc, t1_number, probe_span)
    checks = [
        "CHAIN_ID_EXACT",
        "POOL_BYTECODE_PRESENT",
        "FACTORY_BYTECODE_PRESENT",
        "POOL_TOKEN_IDENTITY_EXACT",
        "POOL_FACTORY_EXACT",
        "T1_HISTORICAL_BLOCK_RETRIEVABLE",
        "BOUNDED_SYNC_LOG_RETRIEVAL",
        "REPEATED_REQUEST_DETERMINISTIC",
        "WHOLE_EQUALS_SPLIT_RANGE",
        "HISTORICAL_RECEIPT_RETRIEVABLE",
        "RAW_SYNC_ECONOMIC_DATA_NOT_SERIALIZED",
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
        "t1_block": {
            "number": t1_number,
            "hash": t1["hash"].lower(),
            "timestamp": t1_timestamp,
        },
        "bounded_probe": probe,
        "checks": checks,
        "raw_log_data_serialized": False,
        "candidate_evaluation_performed": False,
        "outer_access_performed": False,
    }


def material_identity(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "chain_id": receipt["chain_id"],
        "pool": receipt["pool"],
        "factory": receipt["factory"],
        "tokens": sorted((receipt["token0"], receipt["token1"])),
        "t1_block": receipt["t1_block"],
    }


def compare_sources(primary: Mapping[str, Any], secondary: Mapping[str, Any]) -> None:
    if material_identity(primary) != material_identity(secondary):
        raise QualificationError("STOP_SOURCE_CONFLICT: material cross-provider identity disagreement")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def assert_canonical_stage_b_authority(root: Path = Path(".")) -> None:
    branch = _git(root, "branch", "--show-current")
    if branch != "master":
        raise QualificationError("real source qualification is forbidden outside canonical master")
    registry = tomllib.loads((root / "docs/state/projects.toml").read_text(encoding="utf-8"))["project"]
    rows = {row["project_id"]: row for row in registry}
    current = rows.get(PROJECT_ID)
    predecessor = rows.get(PREDECESSOR_ID)
    if not current or current.get("state") != "ACTIVE_RESEARCH" or current.get("implementation_authorized") is not True:
        raise QualificationError("canonical Stage-B ACTIVE_RESEARCH authority is absent")
    if not predecessor or predecessor.get("state") != "CLOSED_PASS" or predecessor.get("implementation_authorized") is not False:
        raise QualificationError("Stage-A predecessor is not closed before Stage-B network authority")


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
