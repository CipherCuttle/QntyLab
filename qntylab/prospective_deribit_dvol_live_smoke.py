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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from qntylab.prospective_deribit_dvol import (
    BINANCE_KLINES_URL, DERIBIT_CHANNELS, EXPECTED_PROTOCOL_SHA256,
    ProtocolError, ValidationError, build_deribit_subscription_request,
    load_frozen_protocol,
)

DERIBIT_ENDPOINT = "wss://www.deribit.com/ws/api/v2"
ACK = "NON_PRIMARY_LIVE_SMOKE"
OPEN_TIMEOUT_SECONDS = 10
CLOSE_TIMEOUT_SECONDS = 5
RECEIVE_TIMEOUT_SECONDS = 90
MAX_MESSAGE_BYTES = 1024 * 1024
_COMMIT = __import__("re").compile(r"[0-9a-f]{40}\Z")


class SmokeBlocked(RuntimeError):
    """A source, gate, or integrity condition prevented a smoke result."""


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


def parse_json(raw: bytes) -> Any:
    def reject(value: str) -> None: raise ValueError(value)
    return json.loads(raw, parse_constant=reject)


def classify_deribit(raw: bytes, *, request_id: int = 1) -> tuple[str, dict[str, Any]]:
    try: obj = parse_json(raw)
    except (ValueError, UnicodeDecodeError): return "MALFORMED_MESSAGE", {}
    if not isinstance(obj, dict): return "OTHER_MESSAGE", {}
    if obj.get("id") == request_id:
        if "error" in obj: raise SmokeBlocked("DERIBIT_JSON_RPC_ERROR")
        result = obj.get("result")
        if result != [DERIBIT_CHANNELS["BTC"], DERIBIT_CHANNELS["ETH"]]:
            raise SmokeBlocked("DERIBIT_ACK_MISMATCH")
        return "SUBSCRIPTION_ACK", {"request_id": request_id}
    if obj.get("method") != "subscription": return "OTHER_MESSAGE", {}
    params = obj.get("params")
    if not isinstance(params, dict): return "MALFORMED_MESSAGE", {}
    channel, data = params.get("channel"), params.get("data")
    if channel not in DERIBIT_CHANNELS.values(): return "UNRELATED_NOTIFICATION", {"channel": channel}
    if not isinstance(data, dict): raise SmokeBlocked("DERIBIT_EXPECTED_CHANNEL_MALFORMED")
    asset = "BTC" if channel == DERIBIT_CHANNELS["BTC"] else "ETH"
    ts, vol = data.get("timestamp"), data.get("volatility")
    if data.get("index_name") != ("btc_usd" if asset == "BTC" else "eth_usd") or not isinstance(ts, int) or isinstance(ts, bool) or not -(2**63) < ts < 2**63 or not isinstance(vol, (int, float)) or isinstance(vol, bool) or not math.isfinite(vol):
        raise SmokeBlocked("DERIBIT_EXPECTED_CHANNEL_MALFORMED")
    return f"VALID_{asset}_DVOL_NOTIFICATION", {"channel": channel, "source_timestamp_ms": ts}


def kline_url(symbol: str, boundary: datetime) -> tuple[str, list[tuple[str, str]]]:
    b = int(boundary.timestamp() * 1000)
    params = [("symbol", symbol), ("interval", "1h"), ("startTime", str(b - 3 * 3_600_000)), ("endTime", str(b - 1)), ("limit", "3")]
    return f"{BINANCE_KLINES_URL}?{urlencode(params)}", params


def validate_klines(raw: bytes, boundary: datetime) -> None:
    try: rows = parse_json(raw)
    except ValueError as exc: raise SmokeBlocked("BINANCE_MALFORMED_RESPONSE") from exc
    if not isinstance(rows, list) or len(rows) != 3: raise SmokeBlocked("BINANCE_ROW_COUNT")
    first = int(boundary.timestamp() * 1000) - 3 * 3_600_000
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < 7 or row[0] != first + i * 3_600_000 or row[6] != row[0] + 3_600_000 - 1 or row[6] > int(boundary.timestamp() * 1000) - 1:
            raise SmokeBlocked("BINANCE_KLINE_TIMING")
        price = row[4]
        if not isinstance(price, str): raise SmokeBlocked("BINANCE_CLOSE_NOT_DECIMAL_TEXT")
        try: value = float(price)
        except ValueError as exc: raise SmokeBlocked("BINANCE_CLOSE_NOT_DECIMAL_TEXT") from exc
        if not math.isfinite(value) or value <= 0: raise SmokeBlocked("BINANCE_CLOSE_NOT_POSITIVE_FINITE")


def write_artifact(root: Path, status: str, reason: str, metadata: dict[str, Any], raw_files: Mapping[str, bytes]) -> str:
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.stage-", dir="/tmp"))
    try:
        for relative, payload in raw_files.items():
            path = stage / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
        for name, value in metadata.items():
            (stage / name).parent.mkdir(parents=True, exist_ok=True); (stage / name).write_bytes(canonical(value))
        flags = {"non_primary_live_smoke": True, "primary_observation": False, "scientific_observation": False, "network_contacted": True, "scheduled_collection_authorized": False, "outcome_retrieved": False, "analysis_executed": False, "qnty_authority": False, "trading_authority": False}
        smoke = dict(flags, smoke_status=status, reason_code=reason)
        (stage / "smoke_status.json").write_bytes(canonical(smoke))
        files = []
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            b = path.read_bytes(); files.append({"path": str(path.relative_to(stage)), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
        manifest = dict(flags, artifact_status="VALID", files=files)
        manifest_bytes = canonical(manifest); (stage / "manifest.json").write_bytes(manifest_bytes)
        (stage / "manifest.sha256").write_text(f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n")
        stage.rename(root)
        return hashlib.sha256(manifest_bytes).hexdigest()
    except BaseException:
        import shutil; shutil.rmtree(stage, ignore_errors=True); raise


async def run_smoke(*, protocol: Any, root: Path, commit: str, ws_connect: Callable[..., Awaitable[Any]], http_get: Callable[[str], tuple[int, Mapping[str, str], bytes]], now: Callable[[], datetime] = utc_now, mono: Callable[[], int] = time.monotonic_ns) -> dict[str, Any]:
    start, start_mono = now(), mono(); raw: dict[str, bytes] = {}; events: list[dict[str, Any]] = []; btc = eth = 0; ack = False; reason = "OK"
    try:
        request = build_deribit_subscription_request(); raw["raw/deribit/subscription-request.payload"] = request
        async with await ws_connect(DERIBIT_ENDPOINT, open_timeout=OPEN_TIMEOUT_SECONDS, close_timeout=CLOSE_TIMEOUT_SECONDS, max_size=MAX_MESSAGE_BYTES, proxy=None) as ws:
            await ws.send(request.decode("utf-8"))
            deadline = time.monotonic() + RECEIVE_TIMEOUT_SECONDS; sequence = 0
            while time.monotonic() < deadline and (not ack or not (btc and eth)):
                message = await asyncio.wait_for(ws.recv(), max(0.01, deadline - time.monotonic()))
                payload = message.encode("utf-8") if isinstance(message, str) else bytes(message)
                sequence += 1; receipt, received_mono = now(), mono()
                if received_mono < start_mono or receipt < start: raise SmokeBlocked("CLOCK_DISCONTINUITY")
                kind, extra = classify_deribit(payload); raw[f"raw/deribit/message-{sequence:06d}.payload"] = payload
                events.append(dict(sequence=sequence, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), receipt_utc=receipt.isoformat(), receipt_monotonic_ns=received_mono, classification=kind, **extra))
                ack |= kind == "SUBSCRIPTION_ACK"; btc += kind == "VALID_BTC_DVOL_NOTIFICATION"; eth += kind == "VALID_ETH_DVOL_NOTIFICATION"
        if not ack: raise SmokeBlocked("DERIBIT_ACK_ABSENT")
        boundary = start.replace(minute=0, second=0, microsecond=0)
        binance = {}
        for symbol in ("BTCUSDT", "ETHUSDT"):
            url, params = kline_url(symbol, boundary); req_start, req_mono = now(), mono(); status_code, headers, body = http_get(url); done, done_mono = now(), mono()
            raw[f"raw/binance/{symbol}.response"] = body
            if status_code != 200: raise SmokeBlocked(f"BINANCE_HTTP_{status_code}")
            validate_klines(body, boundary)
            binance[symbol] = {"validation": "PASS", "url": url, "parameters": params, "status": status_code, "body_sha256": hashlib.sha256(body).hexdigest(), "request_start_utc": req_start.isoformat(), "request_start_monotonic_ns": req_mono, "response_complete_utc": done.isoformat(), "response_complete_monotonic_ns": done_mono, "headers": {k.lower(): v for k,v in headers.items() if k.lower() in {"content-type","date","x-mbx-used-weight","x-mbx-used-weight-1m","retry-after"}}}
        status = "NON_PRIMARY_SMOKE_COMPLETE" if btc and eth else "NON_PRIMARY_SMOKE_PARTIAL"; reason = "ALL_SOURCES_VALID" if btc and eth else "DERIBIT_NOTIFICATION_ABSENCE"
    except SmokeBlocked as exc:
        status, reason, binance = "NON_PRIMARY_SMOKE_BLOCKED", str(exc), {}
    end, end_mono = now(), mono()
    metadata = {"environment.json": {"protocol_sha256": protocol.digest, "repository_commit": commit, "run_start_utc": start.isoformat(), "run_end_utc": end.isoformat(), "run_start_monotonic_ns": start_mono, "run_end_monotonic_ns": end_mono, "deribit_endpoint": DERIBIT_ENDPOINT, "binance_endpoint": BINANCE_KLINES_URL, "python_version": sys.version, "openssl_version": ssl.OPENSSL_VERSION, "proxy_environment_present": any(os.getenv(k) is not None for k in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy"))}, "metadata/deribit-events.json": events, "metadata/binance-requests.json": binance}
    manifest_sha = write_artifact(root, status, reason, metadata, raw)
    return {"status": status, "reason": reason, "manifest_sha256": manifest_sha, "btc": btc, "eth": eth, "ack": ack, "duration_seconds": (end_mono-start_mono)/1e9}


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
    result = asyncio.run(run_smoke(protocol=protocol, root=root, commit=args.repository_commit, ws_connect=live_ws, http_get=stdlib_http))
    print(json.dumps({k: result[k] for k in ("status","reason","manifest_sha256","btc","eth","ack","duration_seconds")}, sort_keys=True)); return 0 if result["status"] != "NON_PRIMARY_SMOKE_BLOCKED" else 2


if __name__ == "__main__": main()
