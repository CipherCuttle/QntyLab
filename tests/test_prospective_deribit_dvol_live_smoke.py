from __future__ import annotations

import asyncio
import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qntylab.prospective_deribit_dvol import build_deribit_subscription_request, load_frozen_protocol
from qntylab.prospective_deribit_dvol_live_smoke import DERIBIT_ENDPOINT, SmokeBlocked, classify_deribit, gate, kline_url, run_smoke, safe_output_root, validate_klines

ROOT = Path(__file__).resolve().parents[1]; PROTOCOL = ROOT / "experiments/prospective/dvol_v0/protocol.json"; SIDECAR = PROTOCOL.with_name("protocol.sha256"); COMMIT = __import__("subprocess").check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()

class WS:
    def __init__(self, messages): self.messages = iter(messages); self.sent = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def send(self, message): self.sent.append(message)
    async def recv(self):
        value = next(self.messages)
        if isinstance(value, BaseException): raise value
        return value

def rows(boundary):
    start = int(boundary.timestamp() * 1000) - 3 * 3_600_000
    return json.dumps([[start + i * 3_600_000, "0", "0", "0", "100.0", "0", start + (i + 1) * 3_600_000 - 1] for i in range(3)]).encode()

def notice(asset):
    return json.dumps({"jsonrpc": "2.0", "method": "subscription", "params": {"channel": f"deribit_volatility_index.{asset.lower()}_usd", "data": {"index_name": f"{asset.lower()}_usd", "timestamp": 1760000000000, "volatility": 50.0}}})

def run(tmp_path, messages, http=lambda _: (200, {"content-type": "application/json"}, None)):
    boundary = datetime(2026, 8, 4, 12, tzinfo=UTC); ws = WS(messages); ticks = iter(boundary + timedelta(seconds=i) for i in range(200)); protocol = load_frozen_protocol(PROTOCOL, SIDECAR)
    def fake_http(url):
        status, headers, body = http(url); return status, headers, rows(boundary) if body is None else body
    async def connect(*args, **kwargs): assert args == (DERIBIT_ENDPOINT,); assert kwargs["proxy"] is None; return ws
    result = asyncio.run(run_smoke(protocol=protocol, root=tmp_path / "smoke", commit=COMMIT, ws_connect=connect, http_get=fake_http, now=lambda: next(ticks), mono=iter(range(1, 1000)).__next__))
    return result, tmp_path / "smoke", ws

@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    original_socket = socket.socket
    def blocked(family=socket.AF_INET, *args, **kwargs):
        if family != socket.AF_UNIX: raise AssertionError("network attempted in offline test")
        return original_socket(family, *args, **kwargs)
    monkeypatch.setattr(socket, "socket", blocked); monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted in offline test"))); monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted in offline test")))

def test_gates_and_urls(tmp_path, monkeypatch):
    def git(_root, *args):
        if args == ("rev-parse", "--show-toplevel"): return str(ROOT)
        if args == ("rev-parse", "HEAD"): return COMMIT
        if args == ("branch", "--show-current"): return "research/dvol-v0-phase1b-live-smoke"
        if args == ("status", "--porcelain"): return ""
        raise AssertionError(args)
    monkeypatch.setattr("qntylab.prospective_deribit_dvol_live_smoke._git", git)
    with pytest.raises(SmokeBlocked): safe_output_root(ROOT / "bad", ROOT)
    with pytest.raises(SmokeBlocked): safe_output_root(Path("/var/tmp/bad"), ROOT)
    with pytest.raises(SmokeBlocked): gate(now=datetime(2026, 8, 3, 0, 5, tzinfo=UTC), root=Path("/tmp/blocked"), repository_root=ROOT, commit=COMMIT, protocol_path=PROTOCOL, sidecar=SIDECAR)
    assert gate(now=datetime(2026, 8, 4, tzinfo=UTC), root=tmp_path / "new", repository_root=ROOT, commit=COMMIT, protocol_path=PROTOCOL, sidecar=SIDECAR).digest
    with pytest.raises(SmokeBlocked, match="REPOSITORY_COMMIT_MISMATCH"):
        gate(now=datetime(2026, 8, 4, tzinfo=UTC), root=tmp_path / "wrong-commit", repository_root=ROOT, commit="a" * 40, protocol_path=PROTOCOL, sidecar=SIDECAR)
    assert build_deribit_subscription_request().startswith(b'{"id":1')
    assert [key for key, _ in kline_url("BTCUSDT", datetime(2026, 8, 4, tzinfo=UTC))[1]] == ["symbol", "interval", "startTime", "endTime", "limit"]

@pytest.mark.parametrize(("payload", "reason"), [
    (b'{"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}', "SUBSCRIPTION_ACK"),
    (b'{"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.eth_usd","deribit_volatility_index.btc_usd"]}', "SUBSCRIPTION_ACK"),
    (b'{"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd"]}', "DERIBIT_ACK_CHANNEL_MISMATCH"),
    (b'{"id":true,"jsonrpc":"2.0","result":[]}', "DERIBIT_ACK_WRONG_ID"),
    (b'{"id":1,"jsonrpc":"1.0","result":[]}', "DERIBIT_ACK_WRONG_JSONRPC"),
    (b'{"id":1,"jsonrpc":"2.0","error":{"code":1}}', "DERIBIT_ACK_ERROR"),
    (b'{"id":1,"id":2}', "DERIBIT_DUPLICATE_JSON_KEY"),
    (b'{"id":1,"jsonrpc":"2.0","result":NaN}', "DERIBIT_NONFINITE_JSON_CONSTANT"),
    (b'\xff', "DERIBIT_MALFORMED_UTF8"), (b'{', "DERIBIT_MALFORMED_JSON"),
])
def test_strict_ack_contract(payload, reason):
    kind, diag = classify_deribit(payload); assert kind == reason
    if kind == "SUBSCRIPTION_ACK": assert diag["same_set_as_requested"] and "returned_channels" in diag

def test_kline_validation():
    boundary = datetime(2026, 8, 4, 12, tzinfo=UTC); assert validate_klines(rows(boundary), boundary) is None; assert validate_klines(b"[]", boundary) == "BINANCE_ROW_COUNT"

def test_complete_artifact_and_truthfulness(tmp_path):
    result, artifact, ws = run(tmp_path, [json.dumps({"id": 1, "jsonrpc": "2.0", "result": ["deribit_volatility_index.btc_usd", "deribit_volatility_index.eth_usd"]}), notice("BTC"), notice("ETH")])
    assert result["status"] == "NON_PRIMARY_SMOKE_COMPLETE" and ws.sent == [build_deribit_subscription_request().decode()]
    assert json.loads((artifact / "smoke_status.json").read_text())["network_contacted"] is False
    assert hashlib.sha256((artifact / "manifest.json").read_bytes()).hexdigest() == (artifact / "manifest.sha256").read_text().split()[0]
    assert "50.0" not in (artifact / "smoke_status.json").read_text()

def test_blocked_ack_retained_and_binance_independent(tmp_path):
    bad = b'{"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd"]}'
    result, artifact, _ = run(tmp_path, [bad])
    assert result["status"] == "NON_PRIMARY_SMOKE_BLOCKED"; assert result["binance"][0]["status"] == result["binance"][1]["status"] == "PASS"
    event = json.loads((artifact / "metadata/deribit-events.json").read_text())[0]
    assert (artifact / "raw/deribit/message-000001.payload").read_bytes() == bad and event["sha256"] == hashlib.sha256(bad).hexdigest()

def test_binance_failures_do_not_suppress_other_source(tmp_path):
    calls = []
    def http(url):
        calls.append(url); return (403 if "BTCUSDT" in url else 200), {"retry-after": "60"}, b"forbidden" if "BTCUSDT" in url else None
    result, artifact, _ = run(tmp_path, [json.dumps({"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}), notice("BTC"), notice("ETH")], http)
    assert result["status"] == "NON_PRIMARY_SMOKE_BLOCKED" and [row["status"] for row in result["binance"]] == ["BLOCKED", "PASS"] and len(calls) == 2
    assert (artifact / "raw/binance/BTCUSDT.response").read_bytes() == b"forbidden"
    assert result["binance"][0]["response_body_sha256"] == hashlib.sha256(b"forbidden").hexdigest()
    assert (artifact / "raw/binance/ETHUSDT.response").exists()

def test_partial_and_connection_block_keep_independent_binance(tmp_path):
    ack = json.dumps({"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]})
    result, artifact, _ = run(tmp_path, [ack, asyncio.TimeoutError()])
    assert result["status"] == "NON_PRIMARY_SMOKE_PARTIAL" and [row["status"] for row in result["binance"]] == ["PASS", "PASS"]
    connection = tmp_path / "connection"; connection.mkdir()
    result, artifact, _ = run(connection, [ConnectionError("offline")])
    assert result["status"] == "NON_PRIMARY_SMOKE_BLOCKED" and [row["status"] for row in result["binance"]] == ["PASS", "PASS"]

def test_malformed_notification_is_retained(tmp_path):
    bad = b'{"jsonrpc":"2.0","method":"subscription","params":{"channel":"deribit_volatility_index.btc_usd","data":{}}}'
    result, artifact, _ = run(tmp_path, [json.dumps({"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}), bad])
    assert result["deribit"]["reason"] == "DERIBIT_EXPECTED_CHANNEL_MALFORMED" and (artifact / "raw/deribit/message-000002.payload").read_bytes() == bad

def test_pre_ack_notification_is_retained_but_not_counted(tmp_path):
    ack = json.dumps({"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]})
    result, artifact, _ = run(tmp_path, [notice("BTC"), ack, notice("ETH"), asyncio.TimeoutError()])
    assert result["status"] == "NON_PRIMARY_SMOKE_PARTIAL"
    events = json.loads((artifact / "metadata/deribit-events.json").read_text())
    assert events[0]["classification"] == "VALID_BTC_DVOL_NOTIFICATION"
    assert result["deribit"]["valid_btc_notification_count"] == 0

@pytest.mark.parametrize("value", [0, None, object()])
def test_invalid_websocket_values_are_retained_and_blocked(tmp_path, value):
    result, artifact, _ = run(tmp_path, [value])
    assert result["deribit"]["reason"] == "DERIBIT_INVALID_TRANSPORT_MESSAGE_TYPE"
    assert (artifact / "raw/deribit/message-000001.payload").exists()

def test_decimal_kline_validation_rejects_nonfinite_and_accepts_extreme_decimal():
    boundary = datetime(2026, 8, 4, 12, tzinfo=UTC)
    assert validate_klines(rows(boundary).replace(b'"100.0"', b'"1e-999999"'), boundary) is None
    assert validate_klines(rows(boundary).replace(b'"100.0"', b'"Infinity"'), boundary) == "BINANCE_CLOSE_NOT_POSITIVE_FINITE"

def test_invalid_execution_mode_is_rejected(tmp_path):
    protocol = load_frozen_protocol(PROTOCOL, SIDECAR)
    async def connect(*_args, **_kwargs): return WS([])
    with pytest.raises(SmokeBlocked, match="INVALID_EXECUTION_MODE"):
        asyncio.run(run_smoke(protocol=protocol, root=tmp_path / "smoke", commit=COMMIT, ws_connect=connect, http_get=lambda _: (200, {}, b"[]"), execution_mode="typo"))

def test_publication_never_replaces_preexisting_directory(tmp_path):
    protocol = load_frozen_protocol(PROTOCOL, SIDECAR); target = tmp_path / "occupied"; target.mkdir(); (target / "sentinel").write_text("keep")
    async def connect(*_args, **_kwargs): return WS([ConnectionError("offline")])
    with pytest.raises(SmokeBlocked, match="OUTPUT_PUBLICATION_COLLISION"):
        asyncio.run(run_smoke(protocol=protocol, root=target, commit=COMMIT, ws_connect=connect, http_get=lambda _:(200, {}, rows(datetime(2026,8,4,12,tzinfo=UTC)))))
    assert (target / "sentinel").read_text() == "keep"
