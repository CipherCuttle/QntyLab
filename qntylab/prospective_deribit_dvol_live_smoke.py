"""Bounded, evidence-first Phase 1B smoke orchestration; live execution is CLI-only."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from qntylab.prospective_deribit_dvol import (
    BINANCE_KLINES_URL, DERIBIT_CHANNELS, EXPECTED_PROTOCOL_SHA256, ProtocolError,
    build_deribit_subscription_request, load_frozen_protocol,
)

DERIBIT_ENDPOINT = "wss://www.deribit.com/ws/api/v2"
PHASE1B_BRANCH = "research/dvol-v0-phase1b-live-smoke"
ACK = "NON_PRIMARY_LIVE_SMOKE"
OPEN_TIMEOUT_SECONDS, CLOSE_TIMEOUT_SECONDS, RECEIVE_TIMEOUT_SECONDS = 10, 5, 90
MAX_MESSAGE_BYTES, MAX_MESSAGES, REQUEST_ID = 1024 * 1024, 999, 1
OFFLINE_TEST_FIXTURE, AUTHORIZED_NON_PRIMARY_LIVE_SMOKE = "OFFLINE_TEST_FIXTURE", "AUTHORIZED_NON_PRIMARY_LIVE_SMOKE"
REQUESTED_CHANNELS = [DERIBIT_CHANNELS["BTC"], DERIBIT_CHANNELS["ETH"]]
_COMMIT = __import__("re").compile(r"[0-9a-f]{40}\Z")


class SmokeBlocked(RuntimeError): pass
class _DuplicateKey(ValueError): pass
class _Nonfinite(ValueError): pass
class ClockIntegrityError(RuntimeError): pass


@dataclass(frozen=True)
class _ArtifactAuthority:
    artifact_kind: str
    execution_mode: str
    non_primary_live_smoke: bool
    network_contacted: bool


_OFFLINE_AUTHORITY = _ArtifactAuthority("OFFLINE_TEST_FIXTURE", OFFLINE_TEST_FIXTURE, False, False)
_LIVE_AUTHORITY = _ArtifactAuthority("NON_PRIMARY_LIVE_SOURCE_SMOKE", AUTHORIZED_NON_PRIMARY_LIVE_SMOKE, True, True)


@dataclass(frozen=True)
class ScriptedMessage:
    payload: bytes | None = None
    error: str | None = None


@dataclass(frozen=True)
class OfflineDeribitScript:
    messages: tuple[ScriptedMessage, ...]
    open_error: str | None = None
    close_error: str | None = None


@dataclass(frozen=True)
class ScriptedHttpResult:
    status: int | None = None
    headers: Mapping[str, str] | None = None
    body: bytes | None = None
    error: str | None = None


@dataclass(frozen=True)
class OfflineBinanceScript:
    btc: ScriptedHttpResult
    eth: ScriptedHttpResult


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def utc_now() -> datetime: return datetime.now(UTC)


def _git(repository_root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repository_root), *args], check=True, text=True, capture_output=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SmokeBlocked("IMPLEMENTATION_GIT_GATE_FAILED") from exc


def safe_output_root(root: Path, repository_root: Path) -> None:
    if root.exists() or root.is_symlink() or "/weeks/" in f"{root}/" or root.name == "weeks": raise SmokeBlocked("INVALID_OR_EXISTING_OUTPUT_ROOT")
    if not root.parent.resolve().is_relative_to(Path("/tmp")) or root.resolve().is_relative_to(repository_root.resolve()): raise SmokeBlocked("OUTPUT_ROOT_NOT_NEW_TMP_OUTSIDE_REPOSITORY")


def gate(*, now: datetime, root: Path, repository_root: Path, commit: str, protocol_path: Path, sidecar: Path) -> Any:
    if now.tzinfo != UTC: raise SmokeBlocked("UTC_CLOCK_REQUIRED")
    if now.weekday() == 0 and (now.hour, now.minute, now.second, now.microsecond) <= (0, 15, 0, 0): raise SmokeBlocked("MONDAY_PRIMARY_INTERLOCK")
    if not _COMMIT.fullmatch(commit): raise SmokeBlocked("INVALID_REPOSITORY_COMMIT")
    if _git(repository_root, "rev-parse", "--show-toplevel") != str(repository_root.resolve()): raise SmokeBlocked("IMPLEMENTATION_REPOSITORY_ROOT_MISMATCH")
    if _git(repository_root, "rev-parse", "HEAD") != commit: raise SmokeBlocked("REPOSITORY_COMMIT_MISMATCH")
    if _git(repository_root, "branch", "--show-current") != PHASE1B_BRANCH: raise SmokeBlocked("IMPLEMENTATION_BRANCH_MISMATCH")
    if _git(repository_root, "status", "--porcelain"): raise SmokeBlocked("DIRTY_IMPLEMENTATION_WORKTREE")
    safe_output_root(root, repository_root)
    try: protocol = load_frozen_protocol(protocol_path, sidecar)
    except (OSError, ProtocolError) as exc: raise SmokeBlocked("PROTOCOL_GATE_FAILED") from exc
    if protocol.digest != EXPECTED_PROTOCOL_SHA256: raise SmokeBlocked("PROTOCOL_GATE_FAILED")
    return protocol


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    answer: dict[str, Any] = {}
    for key, value in pairs:
        if key in answer: raise _DuplicateKey(key)
        answer[key] = value
    return answer

def _constant(value: str) -> None: raise _Nonfinite(value)
def strict_json(raw: bytes) -> Any: return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs, parse_constant=_constant)


def _ack_diagnostics(obj: dict[str, Any], request_id: int) -> tuple[str, dict[str, Any]]:
    diag: dict[str, Any] = {"request_id": obj.get("id"), "requested_channels": REQUESTED_CHANNELS}
    if obj.get("jsonrpc") != "2.0": return "DERIBIT_ACK_WRONG_JSONRPC", diag
    response_id = obj.get("id")
    if not isinstance(response_id, int) or isinstance(response_id, bool) or response_id != request_id: return "DERIBIT_ACK_WRONG_ID", diag
    if "error" in obj: return "DERIBIT_ACK_ERROR", diag
    result = obj.get("result")
    if not isinstance(result, list): return "DERIBIT_ACK_WRONG_RESULT_TYPE", diag
    strings = all(type(item) is str for item in result); returned = result if strings else []
    diag.update(returned_channels=returned, same_order_as_requested=returned == REQUESTED_CHANNELS, same_set_as_requested=strings and set(returned) == set(REQUESTED_CHANNELS), duplicate_count=len(result) - len(set(result)) if strings else 0)
    if not strings or len(result) != 2 or diag["duplicate_count"] or set(returned) != set(REQUESTED_CHANNELS): return "DERIBIT_ACK_CHANNEL_MISMATCH", diag
    return "SUBSCRIPTION_ACK", diag


def classify_deribit(raw: bytes, *, request_id: int = REQUEST_ID) -> tuple[str, dict[str, Any]]:
    try: obj = strict_json(raw)
    except UnicodeDecodeError: return "DERIBIT_MALFORMED_UTF8", {}
    except _DuplicateKey: return "DERIBIT_DUPLICATE_JSON_KEY", {}
    except _Nonfinite: return "DERIBIT_NONFINITE_JSON_CONSTANT", {}
    except json.JSONDecodeError: return "DERIBIT_MALFORMED_JSON", {}
    if not isinstance(obj, dict): return "DERIBIT_NONOBJECT_JSON", {}
    if "id" in obj or "result" in obj or "error" in obj: return _ack_diagnostics(obj, request_id)
    if obj.get("method") != "subscription": return "DERIBIT_OTHER_MESSAGE", {}
    if obj.get("jsonrpc") != "2.0" or not isinstance(obj.get("params"), dict): return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {}
    channel, data = obj["params"].get("channel"), obj["params"].get("data")
    if channel not in REQUESTED_CHANNELS: return "DERIBIT_UNRELATED_NOTIFICATION", {"channel": channel if type(channel) is str else None}
    if not isinstance(data, dict): return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {"channel": channel}
    asset = "BTC" if channel == DERIBIT_CHANNELS["BTC"] else "ETH"; ts, vol = data.get("timestamp"), data.get("volatility")
    if data.get("index_name") != f"{asset.lower()}_usd" or type(ts) is not int or not -(2**63) < ts < 2**63 or type(vol) not in (int, float) or not __import__("math").isfinite(vol): return "DERIBIT_EXPECTED_CHANNEL_MALFORMED", {"channel": channel}
    return f"VALID_{asset}_DVOL_NOTIFICATION", {"channel": channel, "source_timestamp_ms": ts}


def kline_url(symbol: str, boundary: datetime) -> tuple[str, list[tuple[str, str]]]:
    if symbol not in {"BTCUSDT", "ETHUSDT"} or boundary.tzinfo != UTC or boundary.minute or boundary.second or boundary.microsecond: raise ValueError("BINANCE_FROZEN_BOUNDARY_REQUIRED")
    b = int(boundary.timestamp() * 1000); params = [("symbol", symbol), ("interval", "1h"), ("startTime", str(b - 10_800_000)), ("endTime", str(b - 1)), ("limit", "3")]
    return f"{BINANCE_KLINES_URL}?{urlencode(params)}", params


def validate_klines(raw: bytes, boundary: datetime) -> str | None:
    try: rows = strict_json(raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError): return "BINANCE_MALFORMED_RESPONSE"
    if not isinstance(rows, list) or len(rows) != 3: return "BINANCE_ROW_COUNT"
    first = int(boundary.timestamp() * 1000) - 10_800_000
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < 7 or type(row[0]) is not int or type(row[6]) is not int or row[0] != first + i * 3_600_000 or row[6] != row[0] + 3_600_000 - 1: return "BINANCE_KLINE_TIMING"
        if type(row[4]) is not str: return "BINANCE_CLOSE_NOT_DECIMAL_TEXT"
        try: value = Decimal(row[4])
        except InvalidOperation: return "BINANCE_CLOSE_NOT_DECIMAL_TEXT"
        if not value.is_finite() or value <= 0: return "BINANCE_CLOSE_NOT_POSITIVE_FINITE"
    return None


def _event(sequence: int, payload: bytes, receipt: datetime, receipt_mono: int) -> dict[str, Any]: return {"sequence": sequence, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "receipt_utc": receipt.isoformat(), "receipt_monotonic_ns": receipt_mono}


def _publish_no_replace(stage: Path, root: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True); result = libc.renameat2(-100, os.fsencode(stage), -100, os.fsencode(root), 1) # RENAME_NOREPLACE
    if result != 0:
        errno = ctypes.get_errno()
        if errno in (17, 39): raise SmokeBlocked("OUTPUT_PUBLICATION_COLLISION")
        raise OSError(errno, os.strerror(errno))


def _write_artifact(root: Path, status: str, reason: str, metadata: Mapping[str, Any], raw_files: Mapping[str, bytes], *, protocol_sha256: str, repository_commit: str, authority: _ArtifactAuthority) -> str:
    if authority is not _OFFLINE_AUTHORITY and authority is not _LIVE_AUTHORITY: raise SmokeBlocked("INVALID_ARTIFACT_AUTHORITY")
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.stage-", dir="/tmp"))
    try:
        for relative, payload in raw_files.items():
            path = stage / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
        for name, value in metadata.items():
            path = stage / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(value))
        flags = {"artifact_kind": authority.artifact_kind, "non_primary_live_smoke": authority.non_primary_live_smoke, "primary_observation": False, "scientific_observation": False, "network_contacted": authority.network_contacted, "execution_mode": authority.execution_mode, "scheduled_collection_authorized": False, "outcome_retrieved": False, "analysis_executed": False, "qnty_authority": False, "trading_authority": False}
        summary = dict(flags, protocol_sha256=protocol_sha256, repository_commit=repository_commit, smoke_status=status, reason_code=reason, run_start_utc=metadata["environment.json"]["run_start_utc"], run_end_utc=metadata["environment.json"]["run_end_utc"])
        (stage / "smoke_status.json").write_bytes(canonical(summary)); files = []
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            body = path.read_bytes(); files.append({"path": str(path.relative_to(stage)), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
        manifest = dict(summary, artifact_status="VALID", source_statuses={"deribit": metadata["metadata/deribit-result.json"], "binance": metadata["metadata/binance-results.json"]}, files=files)
        manifest_bytes = canonical(manifest); (stage / "manifest.json").write_bytes(manifest_bytes); (stage / "manifest.sha256").write_text(f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n")
        _publish_no_replace(stage, root); return hashlib.sha256(manifest_bytes).hexdigest()
    except BaseException:
        import shutil; shutil.rmtree(stage, ignore_errors=True); raise


@dataclass
class Clock:
    now: Callable[[], datetime]; mono: Callable[[], int]; last_utc: datetime; last_mono: int
    def sample(self) -> tuple[datetime, int]:
        utc, monotonic = self.now(), self.mono()
        if utc < self.last_utc or monotonic < self.last_mono: raise ClockIntegrityError
        self.last_utc, self.last_mono = utc, monotonic; return utc, monotonic


async def _deribit_probe(*, ws_connect: Callable[..., Awaitable[Any]], raw: dict[str, bytes], events: list[dict[str, Any]], clock: Clock, start_mono: int) -> dict[str, Any]:
    result: dict[str, Any] = {"source":"DERIBIT", "attempted":True, "network_attempt_count":1, "status":"BLOCKED", "reason":"DERIBIT_ACK_ABSENT", "start_utc":None, "start_monotonic_ns":None, "end_utc":None, "end_monotonic_ns":None, "endpoint":DERIBIT_ENDPOINT, "connection_started_utc":None, "connection_started_monotonic_ns":None, "connection_completed_utc":None, "connection_completed_monotonic_ns":None, "subscription_sent":False, "acknowledgement_received":False, "acknowledgement_valid":False, "acknowledgement_diagnostics":{}, "valid_btc_notification_count":0, "valid_eth_notification_count":0, "message_count":0, "transport_closed_cleanly":False}
    request = build_deribit_subscription_request(); raw["raw/deribit/subscription-request.payload"] = request
    try:
        start, sm = clock.sample(); result.update(start_utc=start.isoformat(), start_monotonic_ns=sm, connection_started_utc=start.isoformat(), connection_started_monotonic_ns=sm)
        async with await ws_connect(DERIBIT_ENDPOINT, open_timeout=OPEN_TIMEOUT_SECONDS, close_timeout=CLOSE_TIMEOUT_SECONDS, max_size=MAX_MESSAGE_BYTES, proxy=None) as ws:
            await ws.send(request.decode()); deadline = clock.mono() + RECEIVE_TIMEOUT_SECONDS * 1_000_000_000; result["subscription_sent"] = True
            for sequence in range(1, MAX_MESSAGES + 1):
                remaining = deadline - clock.mono()
                if remaining <= 0: result["reason"] = "DERIBIT_RECEIVE_TIMEOUT_AFTER_ACK" if result["acknowledgement_valid"] else "DERIBIT_RECEIVE_TIMEOUT_BEFORE_ACK"; break
                try: message = await asyncio.wait_for(ws.recv(), remaining / 1_000_000_000)
                except asyncio.TimeoutError: result["reason"] = "DERIBIT_RECEIVE_TIMEOUT_AFTER_ACK" if result["acknowledgement_valid"] else "DERIBIT_RECEIVE_TIMEOUT_BEFORE_ACK"; break
                except StopAsyncIteration: result["reason"] = "DERIBIT_CLOSED_AFTER_ACK" if result["acknowledgement_valid"] else "DERIBIT_CLOSED_BEFORE_ACK"; break
                if not isinstance(message, (str, bytes, bytearray, memoryview)):
                    payload = repr(message).encode("utf-8", "backslashreplace"); invalid_type = True
                else: payload, invalid_type = (message.encode() if isinstance(message, str) else bytes(message)), False
                try: receipt, receipt_mono = clock.sample()
                except ClockIntegrityError:
                    receipt, receipt_mono = clock.last_utc, clock.last_mono; raw[f"raw/deribit/message-{sequence:06d}.payload"] = payload; entry = _event(sequence,payload,receipt,receipt_mono); entry.update(classification="CLOCK_DISCONTINUITY", reason="CLOCK_DISCONTINUITY"); events.append(entry); result.update(message_count=sequence, reason="CLOCK_DISCONTINUITY"); break
                raw[f"raw/deribit/message-{sequence:06d}.payload"] = payload; entry = _event(sequence,payload,receipt,receipt_mono); events.append(entry); result["message_count"] = sequence
                if invalid_type: entry.update(classification="DERIBIT_INVALID_TRANSPORT_MESSAGE_TYPE", reason="DERIBIT_INVALID_TRANSPORT_MESSAGE_TYPE"); result["reason"]="DERIBIT_INVALID_TRANSPORT_MESSAGE_TYPE"; break
                kind, diagnostics = classify_deribit(payload); entry.update(classification=kind, diagnostics=diagnostics)
                if kind.startswith("DERIBIT_ACK") or kind == "SUBSCRIPTION_ACK":
                    result.update(acknowledgement_received=True, acknowledgement_diagnostics=diagnostics)
                    if kind == "SUBSCRIPTION_ACK": result["acknowledgement_valid"] = True
                    else: result["reason"] = kind; break
                elif kind in {"VALID_BTC_DVOL_NOTIFICATION", "VALID_ETH_DVOL_NOTIFICATION"}:
                    if result["acknowledgement_valid"]: result["valid_btc_notification_count" if "BTC" in kind else "valid_eth_notification_count"] += 1
                elif kind in {"DERIBIT_MALFORMED_UTF8","DERIBIT_MALFORMED_JSON","DERIBIT_DUPLICATE_JSON_KEY","DERIBIT_NONFINITE_JSON_CONSTANT","DERIBIT_EXPECTED_CHANNEL_MALFORMED"}: result["reason"] = kind; break
                if result["acknowledgement_valid"] and result["valid_btc_notification_count"] and result["valid_eth_notification_count"]: result.update(status="PASS", reason="OK"); break
            else: result["reason"] = "DERIBIT_MESSAGE_LIMIT"
        result["transport_closed_cleanly"] = True
    except ClockIntegrityError: result["reason"] = "CLOCK_DISCONTINUITY"
    except asyncio.TimeoutError: result["reason"] = "DERIBIT_OPEN_TIMEOUT"
    except Exception as exc: result["reason"] = "DERIBIT_TRANSPORT_" + type(exc).__name__.upper()
    finally:
        try: end, em = clock.sample()
        except ClockIntegrityError: result["reason"] = "CLOCK_DISCONTINUITY"; end, em = clock.last_utc, clock.last_mono
        result.update(end_utc=end.isoformat(), end_monotonic_ns=em, connection_completed_utc=end.isoformat(), connection_completed_monotonic_ns=em)
    if result["acknowledgement_valid"] and result["status"] != "PASS" and result["reason"] in {"DERIBIT_RECEIVE_TIMEOUT_AFTER_ACK","DERIBIT_CLOSED_AFTER_ACK","DERIBIT_MESSAGE_LIMIT"}: result.update(status="PARTIAL", reason="DERIBIT_NOTIFICATION_ABSENCE" if result["reason"] != "DERIBIT_MESSAGE_LIMIT" else "DERIBIT_MESSAGE_LIMIT")
    return result


def _binance_probe(symbol: str, boundary: datetime, http_get: Callable[[str], tuple[int, Mapping[str,str],bytes]], raw: dict[str,bytes], clock: Clock) -> dict[str,Any]:
    url, params = kline_url(symbol,boundary); result={"source":"BINANCE","symbol":symbol,"attempted":True,"network_attempt_count":1,"status":"BLOCKED","reason":"BINANCE_UNSET","endpoint":BINANCE_KLINES_URL,"ordered_query_parameters":params,"requested_url":url,"start_utc":None,"start_monotonic_ns":None,"end_utc":None,"end_monotonic_ns":None,"http_status":None,"selected_headers":{},"response_body_sha256":None,"response_byte_count":None,"validation_status":"NOT_VALIDATED"}
    try:
        start,sm=clock.sample(); result.update(start_utc=start.isoformat(),start_monotonic_ns=sm)
        status,headers,body=http_get(url); end,em=clock.sample(); result.update(end_utc=end.isoformat(),end_monotonic_ns=em,http_status=status,selected_headers={k.lower():v for k,v in headers.items() if k.lower() in {"content-type","date","x-mbx-used-weight","x-mbx-used-weight-1m","retry-after"}})
        if not isinstance(body,bytes): raise TypeError("response body is not bytes")
        raw[f"raw/binance/{symbol}.response"]=body; result.update(response_byte_count=len(body),response_body_sha256=hashlib.sha256(body).hexdigest())
        if status != 200: result["reason"]=f"BINANCE_HTTP_{status}"; return result
        invalid=validate_klines(body,boundary)
        if invalid: result.update(reason=invalid,validation_status="BLOCKED"); return result
        result.update(status="PASS",reason="OK",validation_status="PASS")
    except ClockIntegrityError: result["reason"]="CLOCK_DISCONTINUITY"
    except Exception as exc:
        try: end,em=clock.sample(); result.update(end_utc=end.isoformat(),end_monotonic_ns=em)
        except ClockIntegrityError: result["reason"]="CLOCK_DISCONTINUITY"
        if result["reason"] != "CLOCK_DISCONTINUITY": result["reason"]="BINANCE_TRANSPORT_"+type(exc).__name__.upper()
    return result


async def _run_smoke_core(*, protocol: Any, root: Path, commit: str, ws_connect: Callable[...,Awaitable[Any]], http_get: Callable[[str],tuple[int,Mapping[str,str],bytes]], authority: _ArtifactAuthority, now: Callable[[],datetime]=utc_now, mono: Callable[[],int]=time.monotonic_ns) -> dict[str,Any]:
    start,start_mono=now(),mono(); clock=Clock(now,mono,start,start_mono); raw:dict[str,bytes]={}; events:list[dict[str,Any]]=[]
    deribit=await _deribit_probe(ws_connect=ws_connect,raw=raw,events=events,clock=clock,start_mono=start_mono); binance=[]
    if deribit["reason"] != "CLOCK_DISCONTINUITY":
        boundary=start.replace(minute=0,second=0,microsecond=0)
        for symbol in ("BTCUSDT","ETHUSDT"):
            row=_binance_probe(symbol,boundary,http_get,raw,clock); binance.append(row)
            if row["reason"] == "CLOCK_DISCONTINUITY": break
    while len(binance)<2: binance.append({"source":"BINANCE","symbol":("BTCUSDT","ETHUSDT")[len(binance)],"attempted":False,"network_attempt_count":0,"status":"BLOCKED","reason":"GLOBAL_CLOCK_INTEGRITY_FAILURE","start_utc":None,"start_monotonic_ns":None,"end_utc":None,"end_monotonic_ns":None,"endpoint":BINANCE_KLINES_URL,"response_body_sha256":None})
    all_binance=all(x["status"]=="PASS" for x in binance)
    if deribit["status"]=="PASS" and all_binance: status,reason="NON_PRIMARY_SMOKE_COMPLETE","ALL_SOURCES_VALID"
    elif deribit["status"]=="PARTIAL" and deribit["reason"]=="DERIBIT_NOTIFICATION_ABSENCE" and all_binance: status,reason="NON_PRIMARY_SMOKE_PARTIAL","DERIBIT_NOTIFICATION_ABSENCE"
    else: status,reason="NON_PRIMARY_SMOKE_BLOCKED",("CLOCK_DISCONTINUITY" if deribit["reason"]=="CLOCK_DISCONTINUITY" or any(x["reason"]=="CLOCK_DISCONTINUITY" for x in binance) else deribit["reason"] if deribit["status"]=="BLOCKED" else next(x["reason"] for x in binance if x["status"]!="PASS"))
    try: end,end_mono=clock.sample()
    except ClockIntegrityError: end,end_mono=clock.last_utc,clock.last_mono; status,reason="NON_PRIMARY_SMOKE_BLOCKED","CLOCK_DISCONTINUITY"
    environment={"protocol_sha256":protocol.digest,"repository_commit":commit,"run_start_utc":start.isoformat(),"run_end_utc":end.isoformat(),"run_start_monotonic_ns":start_mono,"run_end_monotonic_ns":end_mono,"deribit_endpoint":DERIBIT_ENDPOINT,"binance_endpoint":BINANCE_KLINES_URL,"execution_mode":authority.execution_mode,"python_version":sys.version,"platform":platform.platform(),"openssl_version":ssl.OPENSSL_VERSION}
    manifest_sha=_write_artifact(root,status,reason,{"environment.json":environment,"metadata/deribit-events.json":events,"metadata/deribit-result.json":deribit,"metadata/binance-results.json":binance},raw,protocol_sha256=protocol.digest,repository_commit=commit,authority=authority)
    return {"status":status,"reason":reason,"manifest_sha256":manifest_sha,"deribit":deribit,"binance":binance,"duration_seconds":(end_mono-start_mono)/1e9}


def stdlib_http(url: str) -> tuple[int,Mapping[str,str],bytes]:
    opener=build_opener(ProxyHandler({}))
    try:
        with opener.open(Request(url),timeout=10) as response: return response.status,dict(response.headers.items()),response.read()
    except HTTPError as exc:
        with exc: return exc.code,dict(exc.headers.items()) if exc.headers else {},exc.read()

async def live_ws(*args:Any,**kwargs:Any)->Any:
    import websockets
    return websockets.connect(*args,**kwargs)


class _OfflineWebSocket:
    def __init__(self, script: OfflineDeribitScript): self._messages = iter(script.messages); self._close_error = script.close_error
    async def __aenter__(self) -> "_OfflineWebSocket": return self
    async def __aexit__(self, *_args: Any) -> bool:
        if self._close_error: raise RuntimeError(self._close_error)
        return False
    async def send(self, _message: str) -> None: pass
    async def recv(self) -> bytes:
        message = next(self._messages)
        if message.error == "TIMEOUT": raise asyncio.TimeoutError
        if message.error: raise RuntimeError(message.error)
        if message.payload is None: raise RuntimeError("SCRIPTED_MESSAGE_MISSING_PAYLOAD")
        return message.payload


async def _offline_ws_connect(script: OfflineDeribitScript, *_args: Any, **_kwargs: Any) -> _OfflineWebSocket:
    if script.open_error == "TIMEOUT": raise asyncio.TimeoutError
    if script.open_error: raise RuntimeError(script.open_error)
    return _OfflineWebSocket(script)


def _offline_http_get(script: OfflineBinanceScript, url: str) -> tuple[int, Mapping[str, str], bytes]:
    result = script.btc if "BTCUSDT" in url else script.eth if "ETHUSDT" in url else None
    if result is None: raise RuntimeError("UNSCRIPTED_SYMBOL")
    if result.error: raise RuntimeError(result.error)
    if result.status is None or result.body is None: raise RuntimeError("SCRIPTED_HTTP_RESULT_INCOMPLETE")
    return result.status, result.headers or {}, result.body


async def run_offline_fixture(*, protocol: Any, root: Path, commit: str, deribit_script: OfflineDeribitScript, binance_script: OfflineBinanceScript, now: Callable[[], datetime] = utc_now, mono: Callable[[], int] = time.monotonic_ns) -> dict[str, Any]:
    """Execute inert in-memory fixture data; this API accepts no transport callbacks."""
    return await _run_smoke_core(protocol=protocol, root=root, commit=commit, ws_connect=lambda *args, **kwargs: _offline_ws_connect(deribit_script, *args, **kwargs), http_get=lambda url: _offline_http_get(binance_script, url), authority=_OFFLINE_AUTHORITY, now=now, mono=mono)


async def _run_authorized_live_smoke(*, protocol: Any, root: Path, commit: str, now: Callable[[], datetime] = utc_now, mono: Callable[[], int] = time.monotonic_ns) -> dict[str, Any]:
    """The only live path; its adapters and artifact authority are module-owned."""
    return await _run_smoke_core(protocol=protocol, root=root, commit=commit, ws_connect=live_ws, http_get=stdlib_http, authority=_LIVE_AUTHORITY, now=now, mono=mono)

def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="command",required=True); r=s.add_parser("run-non-primary-smoke")
    for name in ("--protocol","--sidecar","--repository-commit","--output-root","--acknowledge-non-primary"): r.add_argument(name,required=True)
    return p

def main(argv:list[str]|None=None)->int:
    args=parser().parse_args(argv)
    if args.acknowledge_non_primary!=ACK: raise SmokeBlocked("ACKNOWLEDGEMENT_REQUIRED")
    repo=Path.cwd().resolve(); protocol=gate(now=utc_now(),root=Path(args.output_root),repository_root=repo,commit=args.repository_commit,protocol_path=Path(args.protocol),sidecar=Path(args.sidecar))
    result=asyncio.run(_run_authorized_live_smoke(protocol=protocol,root=Path(args.output_root),commit=args.repository_commit)); print(json.dumps({k:result[k] for k in ("status","reason","manifest_sha256","duration_seconds")},sort_keys=True)); return 0 if result["status"]!="NON_PRIMARY_SMOKE_BLOCKED" else 2

if __name__=="__main__": main()
