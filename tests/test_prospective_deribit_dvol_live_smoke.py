from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import socket
import subprocess
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import qntylab.prospective_deribit_dvol_live_smoke as smoke
from qntylab.prospective_deribit_dvol import build_deribit_subscription_request, load_frozen_protocol
from qntylab.prospective_deribit_dvol_live_smoke import (
    AUTHORIZED_NON_PRIMARY_LIVE_SMOKE, DERIBIT_ENDPOINT, OfflineBinanceScript,
    OfflineDeribitScript, ScriptedHttpResult, ScriptedMessage, SmokeBlocked,
    _run_authorized_live_smoke,
    classify_deribit, gate, kline_url, parser, run_offline_fixture,
    _write_offline_fixture_artifact, safe_output_root, validate_klines,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/prospective/dvol_v0/protocol.json"
SIDECAR = PROTOCOL.with_name("protocol.sha256")
COMMIT = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def rows(boundary: datetime) -> bytes:
    start = int(boundary.timestamp() * 1000) - 3 * 3_600_000
    return json.dumps([[start + i * 3_600_000, "0", "0", "0", "100.0", "0", start + (i + 1) * 3_600_000 - 1] for i in range(3)]).encode()


def notice(asset: str) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "method": "subscription", "params": {"channel": f"deribit_volatility_index.{asset.lower()}_usd", "data": {"index_name": f"{asset.lower()}_usd", "timestamp": 1760000000000, "volatility": 50.0}}}).encode()


def complete_script(*messages: ScriptedMessage, btc: ScriptedHttpResult | None = None, eth: ScriptedHttpResult | None = None, open_error: str | None = None) -> tuple[OfflineDeribitScript, OfflineBinanceScript]:
    boundary = datetime(2026, 8, 4, 12, tzinfo=UTC)
    default = ScriptedHttpResult(200, {"content-type": "application/json"}, rows(boundary))
    return OfflineDeribitScript(messages, open_error=open_error), OfflineBinanceScript(btc or default, eth or default)


def run(tmp_path: Path, deribit: OfflineDeribitScript, binance: OfflineBinanceScript, *, times: list[datetime] | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    boundary = datetime(2026, 8, 4, 12, tzinfo=UTC)
    ticks = iter(times or [boundary + timedelta(seconds=i) for i in range(200)])
    return asyncio.run(run_offline_fixture(protocol=load_frozen_protocol(PROTOCOL, SIDECAR), root=tmp_path / "smoke", commit=COMMIT, deribit_script=deribit, binance_script=binance, now=lambda: next(ticks), mono=iter(range(1, 1000)).__next__))


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def blocked(*_args, **_kwargs): raise AssertionError("network attempted in offline test")
    original_socket = socket.socket
    monkeypatch.setattr(socket, "socket", lambda family=socket.AF_INET, *a, **k: original_socket(family, *a, **k) if family == socket.AF_UNIX else blocked())
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", blocked)
    import urllib.request
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    original_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda args, *a, **k: blocked() if args and args[0] in {"curl", "wget"} else original_run(args, *a, **k))
    try:
        import websockets
        monkeypatch.setattr(websockets, "connect", blocked)
    except ImportError:
        pass


def test_gates_and_urls(tmp_path, monkeypatch):
    def git(_root, *args):
        return {("rev-parse", "--show-toplevel"): str(ROOT), ("rev-parse", "HEAD"): COMMIT, ("branch", "--show-current"): "research/dvol-v0-phase1b-live-smoke", ("status", "--porcelain"): ""}[args]
    monkeypatch.setattr("qntylab.prospective_deribit_dvol_live_smoke._git", git)
    with pytest.raises(SmokeBlocked): safe_output_root(ROOT / "bad", ROOT)
    assert gate(now=datetime(2026, 8, 4, tzinfo=UTC), root=tmp_path / "new", repository_root=ROOT, commit=COMMIT, protocol_path=PROTOCOL, sidecar=SIDECAR).digest
    assert [key for key, _ in kline_url("BTCUSDT", datetime(2026, 8, 4, tzinfo=UTC))[1]] == ["symbol", "interval", "startTime", "endTime", "limit"]


def test_cli_has_no_execution_mode_option():
    assert "execution_mode" not in vars(parser().parse_args(["run-non-primary-smoke", "--protocol", "x", "--sidecar", "x", "--repository-commit", "x", "--output-root", "x", "--acknowledge-non-primary", "x"]))


def test_authority_wrappers_have_no_callback_or_mode_bypass():
    for function in (_run_authorized_live_smoke, run_offline_fixture):
        params = inspect.signature(function).parameters
        assert "ws_connect" not in params and "http_get" not in params and "execution_mode" not in params
    assert "live_ws" in inspect.getsource(_run_authorized_live_smoke)
    assert "stdlib_http" in inspect.getsource(_run_authorized_live_smoke)
    source = inspect.getsource(smoke)
    assert source.count("live_ws") == 2 and source.count("stdlib_http") == 2


def test_no_callable_mixes_transport_and_artifact_authority():
    """The former shared core allowed live-capable sentinels plus offline identity."""
    forbidden = {"authority", "execution_mode", "network_contacted", "artifact_kind"}
    transports = {"ws_connect", "http_get"}
    for _name, function in inspect.getmembers(smoke, inspect.isfunction):
        parameters = set(inspect.signature(function).parameters)
        assert not (parameters & transports and parameters & forbidden), function.__name__
    assert not hasattr(smoke, "_run_smoke_core")


def test_dedicated_writers_expose_no_identity_selector():
    for function in (smoke._write_offline_fixture_artifact, smoke._write_authorized_live_artifact):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & {"authority", "artifact_kind", "execution_mode", "network_contacted", "non_primary_live_smoke"}
    assert "OFFLINE_TEST_FIXTURE" in inspect.getsource(smoke._write_offline_fixture_artifact)
    assert "NON_PRIMARY_LIVE_SOURCE_SMOKE" in inspect.getsource(smoke._write_authorized_live_artifact)


def test_live_wrapper_hardcodes_live_identity_without_network(monkeypatch, tmp_path):
    captured = {}
    async def core(**kwargs):
        captured.update(kwargs); return ({"status": "stub", "reason": "stub"}, {"deribit": {}, "binance": {}}, {}, [], datetime(2026, 8, 4, tzinfo=UTC), 1, datetime(2026, 8, 4, tzinfo=UTC), 2)
    monkeypatch.setattr(smoke, "_collect_evidence", core)
    monkeypatch.setattr(smoke, "_metadata", lambda **_kwargs: {"environment.json": {"run_start_utc": "x", "run_end_utc": "y"}, "metadata/deribit-result.json": {}, "metadata/binance-results.json": {}})
    monkeypatch.setattr(smoke, "_write_authorized_live_artifact", lambda *_args, **_kwargs: "manifest")
    result = asyncio.run(_run_authorized_live_smoke(protocol=SimpleNamespace(digest="protocol"), root=tmp_path / "live", commit=COMMIT))
    assert result["manifest_sha256"] == "manifest"
    assert captured["ws_connect"] is smoke.live_ws and captured["http_get"] is smoke.stdlib_http


def test_complete_offline_fixture_truthfulness(tmp_path):
    deribit, binance = complete_script(ScriptedMessage(json.dumps({"id": 1, "jsonrpc": "2.0", "result": ["deribit_volatility_index.btc_usd", "deribit_volatility_index.eth_usd"]}).encode()), ScriptedMessage(notice("BTC")), ScriptedMessage(notice("ETH")))
    result = run(tmp_path, deribit, binance); artifact = tmp_path / "smoke"
    status = json.loads((artifact / "smoke_status.json").read_text())
    assert result["status"] == "NON_PRIMARY_SMOKE_COMPLETE"
    assert {key: status[key] for key in ("artifact_kind", "non_primary_live_smoke", "network_contacted", "execution_mode")} == {"artifact_kind": "OFFLINE_TEST_FIXTURE", "non_primary_live_smoke": False, "network_contacted": False, "execution_mode": "OFFLINE_TEST_FIXTURE"}
    assert hashlib.sha256((artifact / "manifest.json").read_bytes()).hexdigest() == (artifact / "manifest.sha256").read_text().split()[0]


def test_partial_and_blocked_cases_retain_independent_scripted_evidence(tmp_path):
    ack = ScriptedMessage(json.dumps({"id":1,"jsonrpc":"2.0","result":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}).encode())
    partial, binance = complete_script(ack, ScriptedMessage(error="TIMEOUT")); assert run(tmp_path / "partial", partial, binance)["status"] == "NON_PRIMARY_SMOKE_PARTIAL"
    blocked, binance = complete_script(ScriptedMessage(error="BLOCKED")); result = run(tmp_path / "blocked", blocked, binance); assert result["status"] == "NON_PRIMARY_SMOKE_BLOCKED" and [item["status"] for item in result["binance"]] == ["PASS", "PASS"]


def test_http_error_and_clock_failure_are_fail_closed(tmp_path):
    deribit, binance = complete_script(ScriptedMessage(error="BLOCKED"), btc=ScriptedHttpResult(403, {"retry-after":"60"}, b"forbidden"))
    result = run(tmp_path / "http", deribit, binance); assert result["binance"][0]["reason"] == "BINANCE_HTTP_403" and result["binance"][1]["status"] == "PASS"
    deribit, binance = complete_script(ScriptedMessage(error="BLOCKED"))
    backwards = [datetime(2026, 8, 4, hour, tzinfo=UTC) for hour in (12, 11, 10, 9, 8)]
    assert run(tmp_path / "clock", deribit, binance, times=backwards)["reason"] == "CLOCK_DISCONTINUITY"


def test_required_offline_fixtures_are_deterministic_and_manifest_complete(tmp_path):
    ack = ScriptedMessage(json.dumps({"id": 1, "jsonrpc": "2.0", "result": ["deribit_volatility_index.btc_usd", "deribit_volatility_index.eth_usd"]}).encode())
    complete, binance = complete_script(ack, ScriptedMessage(notice("BTC")), ScriptedMessage(notice("ETH")))
    assert run(tmp_path / "complete-a", complete, binance)["manifest_sha256"] == run(tmp_path / "complete-b", complete, binance)["manifest_sha256"]
    partial, binance = complete_script(ack, ScriptedMessage(error="TIMEOUT")); assert run(tmp_path / "partial", partial, binance)["status"] == "NON_PRIMARY_SMOKE_PARTIAL"
    blocked, binance = complete_script(ScriptedMessage(error="BLOCKED")); assert run(tmp_path / "ack-blocked", blocked, binance)["status"] == "NON_PRIMARY_SMOKE_BLOCKED"
    connection, binance = complete_script(open_error="CONNECTION"); assert run(tmp_path / "connection-blocked", connection, binance)["deribit"]["reason"] == "DERIBIT_TRANSPORT_RUNTIMEERROR"
    blocked, malformed = complete_script(ScriptedMessage(error="BLOCKED"), eth=ScriptedHttpResult(200, {}, b"not-json")); assert run(tmp_path / "eth-malformed", blocked, malformed)["binance"][1]["reason"] == "BINANCE_MALFORMED_RESPONSE"
    artifact = tmp_path / "complete-a" / "smoke"; manifest = json.loads((artifact / "manifest.json").read_text())
    listed = {entry["path"]: entry for entry in manifest["files"]}
    actual = {str(path.relative_to(artifact)): path for path in artifact.rglob("*") if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}}
    assert set(listed) == set(actual)
    for relative, path in actual.items():
        assert listed[relative]["bytes"] == path.stat().st_size
        assert listed[relative]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_writers_hardcode_identity_and_scripts_validate_and_freeze(tmp_path):
    metadata = {"environment.json": {"run_start_utc": "x", "run_end_utc": "y"}, "metadata/deribit-result.json": {}, "metadata/binance-results.json": {}}
    _write_offline_fixture_artifact(tmp_path / "fixture", "x", "x", metadata, {}, protocol_sha256="x", repository_commit=COMMIT)
    flags = json.loads((tmp_path / "fixture" / "smoke_status.json").read_text())
    assert flags["artifact_kind"] == "OFFLINE_TEST_FIXTURE" and not flags["network_contacted"]
    with pytest.raises(ValueError): ScriptedMessage(b"x", "BLOCKED")
    with pytest.raises(ValueError): ScriptedHttpResult(200, {}, b"x", "BLOCKED")
    with pytest.raises(ValueError): ScriptedHttpResult(True, {}, b"x")
    headers = {"x-test": "before"}; result = ScriptedHttpResult(200, headers, b"x"); headers["x-test"] = "after"
    assert result.headers == {"x-test": "before"}


def test_no_clobber_and_strict_parser(tmp_path):
    target = tmp_path / "occupied"; target.mkdir(); (target / "sentinel").write_text("keep")
    deribit, binance = complete_script(ScriptedMessage(error="BLOCKED"))
    with pytest.raises(SmokeBlocked, match="OUTPUT_PUBLICATION_COLLISION"):
        asyncio.run(run_offline_fixture(protocol=load_frozen_protocol(PROTOCOL, SIDECAR), root=target, commit=COMMIT, deribit_script=deribit, binance_script=binance))
    assert (target / "sentinel").read_text() == "keep"
    assert classify_deribit(b'{"id":1,"id":2}')[0] == "DERIBIT_DUPLICATE_JSON_KEY"
    assert validate_klines(b"[]", datetime(2026, 8, 4, 12, tzinfo=UTC)) == "BINANCE_ROW_COUNT"
