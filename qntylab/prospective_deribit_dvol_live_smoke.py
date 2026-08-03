"""One bounded, non-primary DVOL source smoke; no scheduled collection."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import ssl
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from qntylab.prospective_deribit_dvol import (
    BINANCE_KLINES_URL, DERIBIT_CHANNELS, EXPECTED_PROTOCOL_SHA256, ProtocolError,
    build_deribit_subscription_request, load_frozen_protocol,
)

DERIBIT_ENDPOINT = "wss://www.deribit.com/ws/api/v2"
ACK = "NON_PRIMARY_LIVE_SMOKE"
OPEN_TIMEOUT_SECONDS = 10
CLOSE_TIMEOUT_SECONDS = 5
RECEIVE_TIMEOUT_SECONDS = 90
MAX_MESSAGE_BYTES = 1024 * 1024
_COMMIT = __import__("re").compile(r"[0-9a-f]{40}\Z")
REQUEST_ID = 1
REQUESTED_CHANNELS = [DERIBIT_CHANNELS["BTC"], DERIBIT_CHANNELS["ETH"]]


class SmokeBlocked(RuntimeError):
    """A global gate condition prevented source execution."""


class _DuplicateKey(ValueError):
    pass


class _Nonfinite(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def utc_now() -> datetime:
    return datetime.now(UTC)


def safe_output_root(root: Path, repository_root: Path) -> None:
    root = root.resolve()
    if root.exists() or "/weeks/" in f"{root}/" or root.name == "weeks":
        raise SmokeBlocked("INVALID_OR_EXISTING_OUTPUT_ROOT")
    if not root.is_relative_to(Path("/tmp")) or root.is_relative_to(repository_root.resolve()):
        raise SmokeBlocked("OUTPUT_ROOT_NOT_NEW_TMP_OUTSIDE_REPOSITORY")


def gate(*, now: datetime, root: Path, repository_root: Path, commit: str, protocol_path: Path, sidecar: Path) -> Any:
    if now.tzinfo != UTC:
        raise SmokeBlocked("UTC_CLOCK_REQUIRED")
    if now.weekday() == 0 and (now.hour, now.minute, now.second, now.microsecond) <= (0, 15, 0, 0):
        raise SmokeBlocked("MONDAY_PRIMARY_INTERLOCK")
    if not _COMMIT.fullmatch(commit):
        raise SmokeBlocked("INVALID_REPOSITORY_COMMIT")
    safe_output_root(root, repository_root)
    try:
        protocol = load_frozen_protocol(protocol_path, sidecar)
    except (OSError, ProtocolError) as exc:
        raise SmokeBlocked("PROTOCOL_GATE_FAILED") from exc
    if protocol.digest != EXPECTED_PROTOCOL_SHA256:
        raise SmokeBlocked("PROTOCOL_GATE_FAILED")
    return protocol


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    answer: dict[str, Any] = {}
    for key, value in pairs:
        if key in answer:
            raise _DuplicateKey(key)
        answer[key] = value
    return answer


def _constant(value: str) -> None:
    raise _Nonfinite(value)


def strict_json(raw: bytes) -> Any:
    """Decode only strict JSON; raw bytes are retained before this is called."""
    text = raw.decode("utf-8", errors="strict")
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def _ack_diagnostics(obj: dict[str, Any], request_id: int) -> tuple[str, dict[str, Any]]:
    diag: dict[str, Any] = {"request_id": obj.get("id"), "requested_channels": REQUESTED_CHANNELS}
    if obj.get("jsonrpc") != "2.0":
        return "DERIBIT_ACK_WRONG_JSONRPC", diag
    response_id = obj.get("id")
    if not isinstance(response_id, int) or isinstance(response_id, bool) or response_id != request_id:
        return "DERIBIT_ACK_WRONG_ID", diag
    if "error" in obj:
        return "DERIBIT_ACK_ERROR", diag
    result = obj.get("result")
    if not isinstance(result, list):
        return "DERIBIT_ACK_WRONG_RESULT_TYPE", diag
    strings = all(isinstance(item, str) for item in result)
    duplicates = len(result) - len(set(result)) if strings else 0
    returned = result if strings else []
    diag.update({"returned_channels": returned, "same_order_as_requested": returned == REQUESTED_CHANNELS,
                 "same_set_as_requested": strings and set(returned) == set(REQUESTED_CHANNELS),
                 "missing_count": len(set(REQUESTED_CHANNELS) - set(returned)) if strings else len(REQUESTED_CHANNELS),
                 "extra_count": len(set(returned) - set(REQUESTED_CHANNELS)) if strings else 0,
                 "duplicate_count": duplicates})
    if not strings or len(result) != 2 or duplicates or set(returned) != set(REQUESTED_CHANNELS):
        return "DERIBIT_ACK_CHANNEL_MISMATCH", diag
    return "SUBSCRIPTION_ACK", diag


def classify_deribit(raw: bytes, *, request_id: int = REQUEST_ID) -> tuple[str, dict[str, Any]]:
    """Classify a retained payload without exposing application values in metadata."""
    try:
        obj = strict_json(raw)
    except UnicodeDecodeError:
        return "DERIBIT_MALFORMED_UTF8", {}
    except _DuplicateKey:
        return "DERIBIT_DUPLICATE_JSON_KEY", {}
    except _Nonfinite:
        return "DERIBIT_NONFINITE_JSON_CONSTANT", {}
    except json.JSONDecodeError:
        return "DERIBIT_MALFORMED_JSON", {}
    if not isinstance(obj, dict):
        return "DERIBIT_NONOBJECT_JSON", {}
    if "id" in obj or "result" in obj or "error" in obj:
        return _ack_diagnostics(obj, request_id)
    if obj.get("method") != "subscription":
        return "DERIBIT_OTHER_MESSAGE", {}
    if obj.get("jsonrpc") != "2.0":
        return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {}
    params = obj.get("params")
    if not isinstance(params, dict):
        return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {}
    channel, data = params.get("channel"), params.get("data")
    if channel not in REQUESTED_CHANNELS:
        return "DERIBIT_UNRELATED_NOTIFICATION", {"channel": channel if isinstance(channel, str) else None}
    if not isinstance(data, dict):
        return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {"channel": channel}
    asset = "BTC" if channel == DERIBIT_CHANNELS["BTC"] else "ETH"
    ts, vol = data.get("timestamp"), data.get("volatility")
    if (data.get("index_name") != f"{asset.lower()}_usd" or not isinstance(ts, int) or isinstance(ts, bool)
            or not -(2**63) < ts < 2**63 or not isinstance(vol, (int, float)) or isinstance(vol, bool)
            or not math.isfinite(vol)):
        return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {"channel": channel}
    return f"VALID_{asset}_DVOL_NOTIFICATION", {"channel": channel, "source_timestamp_ms": ts}


def kline_url(symbol: str, boundary: datetime) -> tuple[str, list[tuple[str, str]]]:
    b = int(boundary.timestamp() * 1000)
    params = [("symbol", symbol), ("interval", "1h"), ("startTime", str(b - 3 * 3_600_000)), ("endTime", str(b - 1)), ("limit", "3")]
    return f"{BINANCE_KLINES_URL}?{urlencode(params)}", params


def validate_klines(raw: bytes, boundary: datetime) -> str | None:
    try:
        rows = strict_json(raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return "BINANCE_MALFORMED_RESPONSE"
    if not isinstance(rows, list) or len(rows) != 3:
        return "BINANCE_ROW_COUNT"
    first = int(boundary.timestamp() * 1000) - 3 * 3_600_000
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < 7 or row[0] != first + i * 3_600_000 or row[6] != row[0] + 3_600_000 - 1 or row[6] > int(boundary.timestamp() * 1000) - 1:
            return "BINANCE_KLINE_TIMING"
        if not isinstance(row[4], str):
            return "BINANCE_CLOSE_NOT_DECIMAL_TEXT"
        try:
            value = float(row[4])
        except ValueError:
            return "BINANCE_CLOSE_NOT_DECIMAL_TEXT"
        if not math.isfinite(value) or value <= 0:
            return "BINANCE_CLOSE_NOT_POSITIVE_FINITE"
    return None


def _event(sequence: int, payload: bytes, receipt: datetime, receipt_mono: int) -> dict[str, Any]:
    return {"sequence": sequence, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "receipt_utc": receipt.isoformat(), "receipt_monotonic_ns": receipt_mono}


def write_artifact(root: Path, status: str, reason: str, metadata: Mapping[str, Any], raw_files: Mapping[str, bytes], *, execution_mode: str) -> str:
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.stage-", dir="/tmp"))
    try:
        for relative, payload in raw_files.items():
            path = stage / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
        for name, value in metadata.items():
            path = stage / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(value))
        flags = {"non_primary_live_smoke": True, "primary_observation": False, "scientific_observation": False,
                 "network_contacted": execution_mode == "AUTHORIZED_NON_PRIMARY_LIVE_SMOKE", "execution_mode": execution_mode,
                 "scheduled_collection_authorized": False, "outcome_retrieved": False, "analysis_executed": False,
                 "qnty_authority": False, "trading_authority": False}
        (stage / "smoke_status.json").write_bytes(canonical(dict(flags, smoke_status=status, reason_code=reason)))
        files = []
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            body = path.read_bytes(); files.append({"path": str(path.relative_to(stage)), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
        manifest = dict(flags, artifact_status="VALID", files=files)
        manifest_bytes = canonical(manifest); (stage / "manifest.json").write_bytes(manifest_bytes)
        (stage / "manifest.sha256").write_text(f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n")
        stage.rename(root); return hashlib.sha256(manifest_bytes).hexdigest()
    except BaseException:
        import shutil
        shutil.rmtree(stage, ignore_errors=True)
        raise


async def _deribit_probe(*, ws_connect: Callable[..., Awaitable[Any]], raw: dict[str, bytes], events: list[dict[str, Any]], now: Callable[[], datetime], mono: Callable[[], int], start: datetime, start_mono: int) -> dict[str, Any]:
    result: dict[str, Any] = {"source": "DERIBIT", "attempted": True, "network_attempt_count": 1, "status": "BLOCKED", "reason": "DERIBIT_ACK_ABSENT", "connection_started_utc": None, "connection_started_monotonic_ns": None, "connection_completed_utc": None, "connection_completed_monotonic_ns": None, "subscription_sent": False, "subscription_request_sha256": None, "acknowledgement_received": False, "acknowledgement_valid": False, "acknowledgement_diagnostics": {}, "valid_btc_notification_count": 0, "valid_eth_notification_count": 0, "message_count": 0, "transport_closed_cleanly": False}
    request = build_deribit_subscription_request(); raw["raw/deribit/subscription-request.payload"] = request; result["subscription_request_sha256"] = hashlib.sha256(request).hexdigest()
    try:
        result["connection_started_utc"], result["connection_started_monotonic_ns"] = now().isoformat(), mono()
        async with await ws_connect(DERIBIT_ENDPOINT, open_timeout=OPEN_TIMEOUT_SECONDS, close_timeout=CLOSE_TIMEOUT_SECONDS, max_size=MAX_MESSAGE_BYTES, proxy=None) as ws:
            await ws.send(request.decode("utf-8")); result["subscription_sent"] = True
            for sequence in range(1, 1000):
                try:
                    message = await asyncio.wait_for(ws.recv(), RECEIVE_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    result["reason"] = "DERIBIT_RECEIVE_TIMEOUT_AFTER_ACK" if result["acknowledgement_valid"] else "DERIBIT_RECEIVE_TIMEOUT_BEFORE_ACK"; break
                except StopAsyncIteration:
                    result["reason"] = "DERIBIT_CLOSED_AFTER_ACK" if result["acknowledgement_valid"] else "DERIBIT_CLOSED_BEFORE_ACK"; break
                payload = message.encode("utf-8") if isinstance(message, str) else bytes(message)
                receipt, receipt_mono = now(), mono(); raw[f"raw/deribit/message-{sequence:06d}.payload"] = payload
                entry = _event(sequence, payload, receipt, receipt_mono); events.append(entry); result["message_count"] += 1
                if receipt < start or receipt_mono < start_mono:
                    entry.update({"classification": "CLOCK_DISCONTINUITY", "reason": "CLOCK_DISCONTINUITY"}); result["reason"] = "CLOCK_DISCONTINUITY"; break
                kind, diagnostics = classify_deribit(payload); entry.update({"classification": kind, "diagnostics": diagnostics})
                if kind.startswith("DERIBIT_ACK") or kind == "SUBSCRIPTION_ACK":
                    result["acknowledgement_received"] = True; result["acknowledgement_diagnostics"] = diagnostics
                    if kind == "SUBSCRIPTION_ACK": result["acknowledgement_valid"] = True
                    else: result["reason"] = kind; break
                elif kind == "VALID_BTC_DVOL_NOTIFICATION": result["valid_btc_notification_count"] += 1
                elif kind == "VALID_ETH_DVOL_NOTIFICATION": result["valid_eth_notification_count"] += 1
                elif kind in {"DERIBIT_MALFORMED_UTF8", "DERIBIT_MALFORMED_JSON", "DERIBIT_DUPLICATE_JSON_KEY", "DERIBIT_NONFINITE_JSON_CONSTANT", "DERIBIT_EXPECTED_CHANNEL_MALFORMED"}:
                    result["reason"] = kind; break
                if result["acknowledgement_valid"] and result["valid_btc_notification_count"] and result["valid_eth_notification_count"]:
                    result.update(status="PASS", reason="OK"); break
            else: result["reason"] = "DERIBIT_NOTIFICATION_ABSENCE"
        result["transport_closed_cleanly"] = True
    except asyncio.TimeoutError: result["reason"] = "DERIBIT_OPEN_TIMEOUT"
    except Exception as exc: result["reason"] = "DERIBIT_TRANSPORT_" + type(exc).__name__.upper()
    finally:
        result["connection_completed_utc"], result["connection_completed_monotonic_ns"] = now().isoformat(), mono()
    if result["acknowledgement_valid"] and result["status"] != "PASS" and result["reason"] in {"DERIBIT_RECEIVE_TIMEOUT_AFTER_ACK", "DERIBIT_CLOSED_AFTER_ACK", "DERIBIT_NOTIFICATION_ABSENCE"}:
        result.update(status="PARTIAL", reason="DERIBIT_NOTIFICATION_ABSENCE")
    return result


def _binance_probe(symbol: str, boundary: datetime, http_get: Callable[[str], tuple[int, Mapping[str, str], bytes]], raw: dict[str, bytes], now: Callable[[], datetime], mono: Callable[[], int]) -> dict[str, Any]:
    url, params = kline_url(symbol, boundary)
    result: dict[str, Any] = {"source": "BINANCE", "symbol": symbol, "attempted": True, "network_attempt_count": 1, "status": "BLOCKED", "reason": "BINANCE_UNSET", "endpoint": BINANCE_KLINES_URL, "ordered_query_parameters": params, "requested_url": url, "request_start_utc": now().isoformat(), "request_start_monotonic_ns": mono(), "response_complete_utc": None, "response_complete_monotonic_ns": None, "http_status": None, "selected_headers": {}, "response_body_sha256": None, "response_byte_count": None, "validation_status": "NOT_VALIDATED"}
    try:
        status, headers, body = http_get(url); result["response_complete_utc"], result["response_complete_monotonic_ns"] = now().isoformat(), mono(); result["http_status"] = status
        result["selected_headers"] = {k.lower(): v for k, v in headers.items() if k.lower() in {"content-type", "date", "x-mbx-used-weight", "x-mbx-used-weight-1m", "retry-after"}}
        raw[f"raw/binance/{symbol}.response"] = body; result["response_byte_count"] = len(body); result["response_body_sha256"] = hashlib.sha256(body).hexdigest()
        if status != 200: result["reason"] = f"BINANCE_HTTP_{status}"; return result
        invalid = validate_klines(body, boundary)
        if invalid: result.update(reason=invalid, validation_status="BLOCKED"); return result
        result.update(status="PASS", reason="OK", validation_status="PASS")
    except Exception as exc:
        result["response_complete_utc"], result["response_complete_monotonic_ns"] = now().isoformat(), mono(); result["reason"] = "BINANCE_TRANSPORT_" + type(exc).__name__.upper()
    return result


async def run_smoke(*, protocol: Any, root: Path, commit: str, ws_connect: Callable[..., Awaitable[Any]], http_get: Callable[[str], tuple[int, Mapping[str, str], bytes]], now: Callable[[], datetime] = utc_now, mono: Callable[[], int] = time.monotonic_ns, execution_mode: str = "FAKE_OFFLINE_TEST") -> dict[str, Any]:
    start, start_mono = now(), mono(); raw: dict[str, bytes] = {}; events: list[dict[str, Any]] = []
    deribit = await _deribit_probe(ws_connect=ws_connect, raw=raw, events=events, now=now, mono=mono, start=start, start_mono=start_mono)
    boundary = start.replace(minute=0, second=0, microsecond=0)
    binance = [_binance_probe(symbol, boundary, http_get, raw, now, mono) for symbol in ("BTCUSDT", "ETHUSDT")]
    all_binance = all(item["status"] == "PASS" for item in binance)
    if deribit["status"] == "PASS" and all_binance: status, reason = "NON_PRIMARY_SMOKE_COMPLETE", "ALL_SOURCES_VALID"
    elif deribit["status"] == "PARTIAL" and deribit["reason"] == "DERIBIT_NOTIFICATION_ABSENCE" and all_binance: status, reason = "NON_PRIMARY_SMOKE_PARTIAL", "DERIBIT_NOTIFICATION_ABSENCE"
    else: status, reason = "NON_PRIMARY_SMOKE_BLOCKED", deribit["reason"] if deribit["status"] == "BLOCKED" else next(item["reason"] for item in binance if item["status"] != "PASS")
    end, end_mono = now(), mono()
    metadata = {"environment.json": {"protocol_sha256": protocol.digest, "repository_commit": commit, "run_start_utc": start.isoformat(), "run_end_utc": end.isoformat(), "run_start_monotonic_ns": start_mono, "run_end_monotonic_ns": end_mono, "deribit_endpoint": DERIBIT_ENDPOINT, "binance_endpoint": BINANCE_KLINES_URL, "execution_mode": execution_mode, "python_version": sys.version, "platform": platform.platform(), "openssl_version": ssl.OPENSSL_VERSION, "proxy_environment_present": any(os.getenv(k) is not None for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"))}, "metadata/deribit-events.json": events, "metadata/deribit-result.json": deribit, "metadata/binance-results.json": binance}
    manifest_sha = write_artifact(root, status, reason, metadata, raw, execution_mode=execution_mode)
    return {"status": status, "reason": reason, "manifest_sha256": manifest_sha, "deribit": deribit, "binance": binance, "duration_seconds": (end_mono - start_mono) / 1e9}


def stdlib_http(url: str) -> tuple[int, Mapping[str, str], bytes]:
    opener = build_opener(ProxyHandler({})); response = opener.open(Request(url), timeout=10)
    return response.status, dict(response.headers.items()), response.read()


async def live_ws(*args: Any, **kwargs: Any) -> Any:
    import websockets
    return websockets.connect(*args, **kwargs)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(); s = p.add_subparsers(dest="command", required=True); r = s.add_parser("run-non-primary-smoke")
    r.add_argument("--protocol", required=True); r.add_argument("--sidecar", required=True); r.add_argument("--repository-commit", required=True); r.add_argument("--output-root", required=True); r.add_argument("--acknowledge-non-primary", required=True); return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.acknowledge_non_primary != ACK: raise SmokeBlocked("ACKNOWLEDGEMENT_REQUIRED")
    root = Path(args.output_root); repo = Path.cwd(); protocol = gate(now=utc_now(), root=root, repository_root=repo, commit=args.repository_commit, protocol_path=Path(args.protocol), sidecar=Path(args.sidecar))
    if os.popen("git status --porcelain").read().strip(): raise SmokeBlocked("DIRTY_IMPLEMENTATION_WORKTREE")
    result = asyncio.run(run_smoke(protocol=protocol, root=root, commit=args.repository_commit, ws_connect=live_ws, http_get=stdlib_http, execution_mode="AUTHORIZED_NON_PRIMARY_LIVE_SMOKE"))
    print(json.dumps({key: result[key] for key in ("status", "reason", "manifest_sha256", "duration_seconds")}, sort_keys=True)); return 0 if result["status"] != "NON_PRIMARY_SMOKE_BLOCKED" else 2


if __name__ == "__main__": main()
