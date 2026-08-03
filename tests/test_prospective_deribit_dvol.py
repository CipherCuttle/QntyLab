from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from qntylab.prospective_deribit_dvol import (
    EXPECTED_PROTOCOL_SHA256, BinanceRequest, RawHttpResponse, SourceEvidence,
    ValidationError, build_binance_trailing_request, build_deribit_subscription_request,
    compute_trailing_realized_volatility, derive_week_timing, fetch_binance_trailing_response,
    load_frozen_protocol, load_recorded_events, parse_and_validate_trailing_klines,
    replay_deribit_formation, write_offline_week_artifact,
)

ROOT=Path(__file__).resolve().parents[1]; PROTOCOL=ROOT/'experiments/prospective/dvol_v0/protocol.json'; SIDECAR=PROTOCOL.with_name('protocol.sha256'); FIXTURES=ROOT/'tests/fixtures/dvol_v0'

def protocol(): return load_frozen_protocol(PROTOCOL,SIDECAR)
def timing(): return derive_week_timing(date(2026,8,3),protocol())
def response_rows(t, n=721):
    return [[t.trailing_start_ms+i*3_600_000,'0','0','0',f'{100+i/10:.8f}','0',t.trailing_start_ms+(i+1)*3_600_000-1] for i in range(n)]
def raw_rows(t,n=721): return json.dumps(response_rows(t,n),separators=(',',':')).encode()

def test_frozen_protocol_load_and_bytes_unchanged():
    assert protocol().digest == EXPECTED_PROTOCOL_SHA256
    assert hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() == EXPECTED_PROTOCOL_SHA256

def test_protocol_sidecar_and_duplicate_or_authority_reject(tmp_path):
    side=tmp_path/'protocol.sha256'; side.write_text(f'{EXPECTED_PROTOCOL_SHA256}  protocol.json\n')
    broken=tmp_path/'protocol.json'; broken.write_bytes(PROTOCOL.read_bytes().replace(b'"network_access_authorized": false',b'"network_access_authorized": true'))
    with pytest.raises(Exception): load_frozen_protocol(broken,side)
    duplicate=tmp_path/'duplicate.json'; duplicate.write_bytes(b'{"a":1,"a":2}')
    with pytest.raises(Exception): load_frozen_protocol(duplicate,side)

def test_timing_exact_and_non_monday_rejected():
    t=timing(); assert t.formation_target.isoformat()=='2026-08-03T00:05:00+00:00'; assert t.formation_acceptance_end.isoformat()=='2026-08-03T00:10:00+00:00'
    assert t.trailing_end_ms == int(t.benchmark_boundary.timestamp()*1000)-1 and t.outcome_start_ms == int((t.final_outcome_boundary).timestamp()*1000)-169*3_600_000
    assert t.earliest_outcome_retrieval == t.final_outcome_boundary.replace(second=0)+__import__('datetime').timedelta(seconds=60)
    with pytest.raises(ValidationError): derive_week_timing(date(2026,8,4),protocol())

def test_subscription_exact_bytes_and_digest():
    value=build_deribit_subscription_request()
    assert value == b'{"id":1,"jsonrpc":"2.0","method":"public/subscribe","params":{"channels":["deribit_volatility_index.btc_usd","deribit_volatility_index.eth_usd"]}}'
    assert hashlib.sha256(value).hexdigest() == 'ba349c41eee6b420658441543d41190dcd056e7bb81b5ec4275f408558720ca3'

def test_formation_fixture_first_valid_wins_and_skipped():
    valid=replay_deribit_formation(protocol=protocol(),timing=timing(),events=load_recorded_events(FIXTURES/'valid_deribit_session.jsonl'))
    assert valid.disposition=='FORMATION_CAPTURED' and valid.accepted['BTC'].value==51.25 and valid.accepted['ETH'].value==61.5
    skipped=replay_deribit_formation(protocol=protocol(),timing=timing(),events=load_recorded_events(FIXTURES/'skipped_deribit_session.jsonl'))
    assert skipped.disposition=='DECLARED_SKIPPED_WEEK' and skipped.reason_code=='TRANSPORT_FAILURE'

def test_formation_rejects_attempt_three_and_sequence_regression():
    events=load_recorded_events(FIXTURES/'skipped_deribit_session.jsonl')
    with pytest.raises(Exception): replay_deribit_formation(protocol=protocol(),timing=timing(),events=[events[0].__class__(3,'x',1,'CONNECTION_OPEN',events[0].receipt_utc,1)])
    with pytest.raises(Exception): replay_deribit_formation(protocol=protocol(),timing=timing(),events=[events[1],events[0]])

def test_binance_request_and_strict_kline_parser():
    t=timing(); request=build_binance_trailing_request(asset='BTC',timing=t,protocol=protocol())
    assert request.parameters == (('symbol','BTCUSDT'),('interval','1h'),('startTime',t.trailing_start_ms),('endTime',t.trailing_end_ms),('limit',721))
    series=parse_and_validate_trailing_klines(raw_response_body=raw_rows(t),request=request,timing=t); assert len(series.closes)==721 and series.closes[0].source_row_index==0
    for bad in (raw_rows(t,720), raw_rows(t,722), b'{}'):
        with pytest.raises(ValidationError): parse_and_validate_trailing_klines(raw_response_body=bad,request=request,timing=t)
    rows=response_rows(t); rows[3],rows[4]=rows[4],rows[3]
    with pytest.raises(ValidationError): parse_and_validate_trailing_klines(raw_response_body=json.dumps(rows).encode(),request=request,timing=t)
    rows=response_rows(t); rows[1][4]='NaN'
    with pytest.raises(ValidationError): parse_and_validate_trailing_klines(raw_response_body=json.dumps(rows).encode(),request=request,timing=t)

def test_volatility_is_sample_annualized_percentage_once():
    request=build_binance_trailing_request(asset='ETH',timing=timing(),protocol=protocol()); series=parse_and_validate_trailing_klines(raw_response_body=raw_rows(timing()),request=request,timing=timing())
    got=compute_trailing_realized_volatility(series); expected=__import__('statistics').stdev([math.log((100+(i+1)/10)/(100+i/10)) for i in range(720)])*math.sqrt(365*24)*100
    assert got.return_count==720 and got.percentage_points == pytest.approx(expected,rel=1e-13)

class FakeClock:
    def __init__(self): self.i=0
    def utc_now(self): self.i+=1; return datetime(2026,8,3,0,5,self.i,tzinfo=UTC)
    def monotonic_ns(self): return self.i
class FakeResponse:
    status_code=200; headers={'Content-Type':'application/json'}; content=b'[]'
class FakeSession:
    def __init__(self): self.calls=0
    def get(self,*args,**kwargs): self.calls+=1; return FakeResponse()
def test_http_helper_injected_no_retry_and_exact_bytes():
    session=FakeSession(); result=fetch_binance_trailing_response(session=session,request=build_binance_trailing_request(asset='BTC',timing=timing(),protocol=protocol()),clock=FakeClock())
    assert session.calls==1 and result.body==b'[]' and result.body_sha256==hashlib.sha256(b'[]').hexdigest()

def test_artifacts_atomic_hash_bound_and_skipped_has_no_binance(tmp_path):
    p=protocol(); t=timing(); events=tuple(load_recorded_events(FIXTURES/'skipped_deribit_session.jsonl')); formation=replay_deribit_formation(protocol=p,timing=t,events=events)
    artifact=write_offline_week_artifact(output_root=tmp_path,protocol=p,timing=t,formation=formation,trailing_series_by_asset=None,trailing_volatility_by_asset=None,source_evidence=SourceEvidence(events),repository_commit='a'*40)
    assert (artifact/'manifest.sha256').read_text().split()[0] == hashlib.sha256((artifact/'manifest.json').read_bytes()).hexdigest()
    status=json.loads((artifact/'week_status.json').read_text()); assert status['scientific_observation'] is False and not (artifact/'raw/binance').exists()
    with pytest.raises(ValidationError): write_offline_week_artifact(output_root=tmp_path,protocol=p,timing=t,formation=formation,trailing_series_by_asset=None,trailing_volatility_by_asset=None,source_evidence=SourceEvidence(events),repository_commit='a'*40)

def test_module_has_no_live_network_surface():
    import qntylab.prospective_deribit_dvol as module
    assert not hasattr(module,'capture_live') and not hasattr(module,'socket')
