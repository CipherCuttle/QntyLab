from __future__ import annotations

import hashlib
import json
import math
import socket
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from qntylab.prospective_deribit_dvol import (
    EXPECTED_PROTOCOL_SHA256, BinanceRequest, RawHttpResponse, SourceEvidence,
    ValidationError, build_binance_trailing_request, build_deribit_subscription_request,
    compute_trailing_realized_volatility, derive_week_timing, load_frozen_protocol,
    load_recorded_events, parse_and_validate_trailing_klines, replay_deribit_formation,
    write_offline_week_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/prospective/dvol_v0/protocol.json"
SIDECAR = PROTOCOL.with_name("protocol.sha256")
FIXTURES = ROOT / "tests/fixtures/dvol_v0"


def protocol():
    return load_frozen_protocol(PROTOCOL, SIDECAR)


def timing():
    return derive_week_timing(date(2026, 8, 3), protocol())


def rows(t, n=721):
    return [[t.trailing_start_ms + i * 3_600_000, "0", "0", "0", f"{100 + i / 10:.8f}", "0", t.trailing_start_ms + (i + 1) * 3_600_000 - 1] for i in range(n)]


def raw_rows(t, n=721):
    return json.dumps(rows(t, n), separators=(",", ":")).encode()


def valid_events():
    return tuple(load_recorded_events(FIXTURES / "valid_deribit_session.jsonl"))


def captured():
    return replay_deribit_formation(protocol=protocol(), timing=timing(), events=valid_events())


def test_protocol_and_timing_are_frozen():
    assert protocol().digest == EXPECTED_PROTOCOL_SHA256
    assert hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() == EXPECTED_PROTOCOL_SHA256
    assert timing().formation_target.isoformat() == "2026-08-03T00:05:00+00:00"
    with pytest.raises(ValidationError):
        derive_week_timing(date(2026, 8, 4), protocol())


@pytest.mark.parametrize("field,value", [("attempt", True), ("attempt", "1"), ("attempt", 1.7), ("sequence", 0), ("receipt_monotonic_ns", -1), ("session_id", {}), ("receipt_utc", "2026-08-03T00:05:00+02:00")])
def test_event_loader_rejects_coercive_or_nonutc_values(tmp_path, field, value):
    item = json.loads((FIXTURES / "skipped_deribit_session.jsonl").read_text().splitlines()[0])
    item[field] = value
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(item) + "\n")
    with pytest.raises(ValidationError):
        load_recorded_events(path)


@pytest.mark.parametrize("content", [b"", b"\n", b'{"attempt":1}\n', b'{"attempt":1,"attempt":1}\n'])
def test_event_loader_rejects_empty_incomplete_and_duplicate_json(tmp_path, content):
    path = tmp_path / "events.jsonl"
    path.write_bytes(content)
    with pytest.raises(ValidationError):
        load_recorded_events(path)


def test_exact_payload_bytes_and_valid_capture():
    events = valid_events()
    assert events[1].payload == build_deribit_subscription_request()
    result = captured()
    assert result.disposition == "FORMATION_CAPTURED"
    assert set(result.accepted) == {"BTC", "ETH"}
    assert result.accepted["BTC"].raw_value_token == "51.25"


@pytest.mark.parametrize("index,change,expected", [
    (1, lambda e: replace(e, receipt_monotonic_ns=100), "LOCAL_OPERATIONAL_FAILURE"),
    (5, lambda e: replace(e, receipt_utc=datetime(2026, 8, 3, 0, 5, 0, tzinfo=UTC)), "LOCAL_OPERATIONAL_FAILURE"),
])
def test_clock_discontinuity_precedes_capture(index, change, expected):
    events = list(valid_events()); events[index] = change(events[index])
    result = replay_deribit_formation(protocol=protocol(), timing=timing(), events=events)
    assert result.disposition == "DECLARED_SKIPPED_WEEK"
    assert result.reason_code == expected


@pytest.mark.parametrize("index,change", [
    (0, lambda e: replace(e, kind="PAYLOAD_RECEIVED", payload=b"{}")),
    (1, lambda e: replace(e, payload=b"{}")),
    (2, lambda e: replace(e, payload=b"not-json")),
    (7, lambda e: replace(e, kind="REQUEST_SENT", payload=b"{}")),
    (0, lambda e: replace(e, attempt=2)),
])
def test_lifecycle_and_integrity_defects_block(index, change):
    events = list(valid_events()); events[index] = change(events[index])
    result = replay_deribit_formation(protocol=protocol(), timing=timing(), events=events)
    assert result.disposition == "BLOCKED"


def test_transport_is_skipped_and_bad_expected_notification_blocks():
    skipped = replay_deribit_formation(protocol=protocol(), timing=timing(), events=load_recorded_events(FIXTURES / "skipped_deribit_session.jsonl"))
    assert (skipped.disposition, skipped.reason_code) == ("DECLARED_SKIPPED_WEEK", "TRANSPORT_FAILURE")
    events = list(valid_events())
    events[4] = replace(events[4], payload=events[4].payload.replace(b'"btc_usd"', b'"eth_usd"'))
    assert replay_deribit_formation(protocol=protocol(), timing=timing(), events=events).disposition == "BLOCKED"


def test_request_identity_rejects_all_variations():
    request = build_binance_trailing_request(asset="BTC", timing=timing(), protocol=protocol())
    bad = [
        replace(request, endpoint="https://wrong"), replace(request, asset="ETH"),
        replace(request, parameters=request.parameters[:-1]),
        replace(request, parameters=tuple(reversed(request.parameters))),
        replace(request, parameters=request.parameters + (("x", "y"),)),
        replace(request, parameters=(("symbol", "ETHUSDT"),) + request.parameters[1:]),
    ]
    for item in bad:
        with pytest.raises(ValidationError):
            parse_and_validate_trailing_klines(raw_response_body=raw_rows(timing()), request=item, timing=timing())


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop(), lambda r: r.append(r[-1]), lambda r: r.__setitem__(1, r[0]),
    lambda r: r[0].__setitem__(0, True), lambda r: r[0].__setitem__(4, 10),
    lambda r: r[0].__setitem__(4, "NaN"), lambda r: r[0].__setitem__(4, "1e2"),
    lambda r: r[0].__setitem__(4, "0"), lambda r: r[0].__setitem__(4, "-1"),
    lambda r: r[0].__setitem__(6, True), lambda r: r[0].__setitem__(6, r[0][6] + 1),
])
def test_kline_parser_rejects_bad_rows(mutation):
    value = rows(timing()); mutation(value)
    request = build_binance_trailing_request(asset="BTC", timing=timing(), protocol=protocol())
    with pytest.raises(ValidationError):
        parse_and_validate_trailing_klines(raw_response_body=json.dumps(value).encode(), request=request, timing=timing())


@pytest.mark.parametrize("body", [b"{}", b"not json", b"[]", b"[{}]", b"[[1,2,3,4,5,6,7]]" * 721])
def test_kline_parser_rejects_bad_top_level(body):
    request = build_binance_trailing_request(asset="BTC", timing=timing(), protocol=protocol())
    with pytest.raises(ValidationError):
        parse_and_validate_trailing_klines(raw_response_body=body, request=request, timing=timing())


def test_volatility_is_sample_annualized_percentage_once():
    request = build_binance_trailing_request(asset="ETH", timing=timing(), protocol=protocol())
    series = parse_and_validate_trailing_klines(raw_response_body=raw_rows(timing()), request=request, timing=timing())
    got = compute_trailing_realized_volatility(series)
    expected = __import__("statistics").stdev([math.log((100 + (i + 1) / 10) / (100 + i / 10)) for i in range(720)]) * math.sqrt(365 * 24) * 100
    assert got.return_count == 720 and got.percentage_points == pytest.approx(expected, rel=1e-13)


def test_artifact_complete_consistent_and_no_overwrite(tmp_path):
    formation = captured(); t = timing(); p = protocol(); series = {}; volatility = {}; responses = {}
    for asset in ("BTC", "ETH"):
        request = build_binance_trailing_request(asset=asset, timing=t, protocol=p); body = raw_rows(t)
        series[asset] = parse_and_validate_trailing_klines(raw_response_body=body, request=request, timing=t)
        volatility[asset] = compute_trailing_realized_volatility(series[asset])
        responses[asset] = RawHttpResponse(request, t.formation_target, 1, t.formation_target, 2, 200, {"content-type": "application/json"}, body, hashlib.sha256(body).hexdigest())
    artifact = write_offline_week_artifact(output_root=tmp_path, protocol=p, timing=t, formation=formation, trailing_series_by_asset=series, trailing_volatility_by_asset=volatility, source_evidence=SourceEvidence(valid_events(), responses), repository_commit="a" * 40)
    manifest = json.loads((artifact / "manifest.json").read_text())
    actual = {str(path.relative_to(artifact)) for path in artifact.rglob("*") if path.is_file()} - {"manifest.json", "manifest.sha256"}
    assert actual == {item["path"] for item in manifest["files"]}
    assert (artifact / "raw/deribit/events.jsonl").exists()
    assert hashlib.sha256((artifact / "manifest.json").read_bytes()).hexdigest() == (artifact / "manifest.sha256").read_text().split()[0]
    with pytest.raises(ValidationError):
        write_offline_week_artifact(output_root=tmp_path, protocol=p, timing=t, formation=formation, trailing_series_by_asset=series, trailing_volatility_by_asset=volatility, source_evidence=SourceEvidence(valid_events(), responses), repository_commit="a" * 40)
    with pytest.raises(ValidationError):
        write_offline_week_artifact(output_root=tmp_path / "other", protocol=p, timing=t, formation=formation, trailing_series_by_asset=None, trailing_volatility_by_asset=None, source_evidence=SourceEvidence(valid_events()), repository_commit="bad")
    bad_responses = dict(responses); bad_responses["BTC"] = replace(bad_responses["BTC"], status=500)
    with pytest.raises(ValidationError):
        write_offline_week_artifact(output_root=tmp_path / "bad-response", protocol=p, timing=t, formation=formation, trailing_series_by_asset=series, trailing_volatility_by_asset=volatility, source_evidence=SourceEvidence(valid_events(), bad_responses), repository_commit="a" * 40)


def test_offline_module_has_no_network_client_or_live_command(monkeypatch, tmp_path):
    import qntylab.prospective_deribit_dvol as module
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert not hasattr(module, "requests")
    assert not hasattr(module, "fetch_binance_trailing_response")
    assert b"capture-live" not in Path(module.__file__).read_bytes()
    assert captured().disposition == "FORMATION_CAPTURED"
