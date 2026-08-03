from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qntylab.prospective_deribit_dvol import build_deribit_subscription_request, load_frozen_protocol
from qntylab.prospective_deribit_dvol_live_smoke import DERIBIT_ENDPOINT, SmokeBlocked, classify_deribit, gate, kline_url, run_smoke, safe_output_root, validate_klines

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/prospective/dvol_v0/protocol.json"
SIDECAR = PROTOCOL.with_name("protocol.sha256")
COMMIT = "a" * 40

class WS:
    def __init__(self, messages): self.messages = iter(messages); self.sent = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def send(self, message): self.sent.append(message)
    async def recv(self): return next(self.messages)

def rows(boundary):
    start = int(boundary.timestamp()*1000)-3*3_600_000
    return json.dumps([[start+i*3_600_000,"0","0","0","100.0","0",start+(i+1)*3_600_000-1] for i in range(3)]).encode()

def notification(asset):
    return json.dumps({"jsonrpc":"2.0","method":"subscription","params":{"channel":f"deribit_volatility_index.{asset.lower()}_usd","data":{"index_name":f"{asset.lower()}_usd","timestamp":1760000000000,"volatility":50.0}}})

def test_import_and_interlocks():
    import qntylab.prospective_deribit_dvol_live_smoke as module
    assert "websockets" not in module.__dict__
    for minute in (0, 5, 10, 15):
        with pytest.raises(SmokeBlocked): gate(now=datetime(2026,8,3,0,minute,tzinfo=UTC), root=Path(f"/tmp/p1b-{minute}"), repository_root=ROOT, commit=COMMIT, protocol_path=PROTOCOL, sidecar=SIDECAR)
    assert gate(now=datetime(2026,8,3,0,16,tzinfo=UTC), root=Path("/tmp/p1b-after"), repository_root=ROOT, commit=COMMIT, protocol_path=PROTOCOL, sidecar=SIDECAR).digest

def test_output_commit_and_contract_gates(tmp_path):
    with pytest.raises(SmokeBlocked): safe_output_root(ROOT / "bad", ROOT)
    with pytest.raises(SmokeBlocked): safe_output_root(Path("/var/tmp/bad"), ROOT)
    existing = tmp_path / "existing"; existing.mkdir()
    with pytest.raises(SmokeBlocked): safe_output_root(existing, ROOT)
    with pytest.raises(SmokeBlocked): gate(now=datetime(2026,8,4,tzinfo=UTC), root=Path("/tmp/p1b-bad"), repository_root=ROOT, commit="A"*40, protocol_path=PROTOCOL, sidecar=SIDECAR)
    assert DERIBIT_ENDPOINT == "wss://www.deribit.com/ws/api/v2"
    assert build_deribit_subscription_request() == b'{"id":1,"jsonrpc":"2.0","method":"public/subscribe","params":{"channels":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}}'

def test_parse_contracts():
    boundary = datetime(2026,8,4,12,tzinfo=UTC); _, params = kline_url("BTCUSDT", boundary)
    assert [x[0] for x in params] == ["symbol","interval","startTime","endTime","limit"]
    validate_klines(rows(boundary), boundary)
    with pytest.raises(SmokeBlocked): validate_klines(b"[]", boundary)
    assert classify_deribit(b'{"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}')[0] == "SUBSCRIPTION_ACK"
    assert classify_deribit(notification("BTC").encode())[0] == "VALID_BTC_DVOL_NOTIFICATION"
    with pytest.raises(SmokeBlocked): classify_deribit(b'{"id":1,"error":{"code":1}}')

def test_complete_artifact(tmp_path):
    protocol = load_frozen_protocol(PROTOCOL, SIDECAR); boundary = datetime(2026,8,4,12,tzinfo=UTC)
    ws = WS([json.dumps({"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}), notification("BTC"), notification("ETH")])
    async def connect(*args, **kwargs): assert args == (DERIBIT_ENDPOINT,); assert kwargs["proxy"] is None; return ws
    ticks = iter([boundary+timedelta(seconds=i) for i in range(40)])
    result = asyncio.run(run_smoke(protocol=protocol, root=tmp_path/"smoke", commit=COMMIT, ws_connect=connect, http_get=lambda url:(200,{"content-type":"application/json"},rows(boundary)), now=lambda:next(ticks), mono=iter(range(1,100)).__next__))
    artifact = tmp_path/"smoke"; assert result["status"] == "NON_PRIMARY_SMOKE_COMPLETE" and ws.sent == [build_deribit_subscription_request().decode()]
    assert hashlib.sha256((artifact/"manifest.json").read_bytes()).hexdigest() == (artifact/"manifest.sha256").read_text().split()[0]
    assert "50.0" not in (artifact/"smoke_status.json").read_text()
