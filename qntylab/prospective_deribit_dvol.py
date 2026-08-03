"""Offline-only replay core for the frozen Deribit DVOL V0 protocol.

This module deliberately has no live capture command or socket implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import stdev
from typing import Any, Iterable, Literal, Mapping, Protocol

import requests

EXPECTED_PROTOCOL_SHA256 = "c4510bab86b6cf7e472499f85dfbf603fe802baa73872fb2b392183ccafea323"
PROTOCOL_ID = "qntylab_deribit_dvol_prospective_forecast_v0"
DERIBIT_CHANNELS = {"BTC": "deribit_volatility_index.btc_usd", "ETH": "deribit_volatility_index.eth_usd"}
BINANCE_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


class ProtocolError(ValueError): pass
class ReplayError(ValueError): pass
class ValidationError(ValueError): pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result: raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None: raise ValidationError(f"non-finite JSON value: {value}")


def _loads(raw: bytes | str) -> Any:
    return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def _utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None: raise ValidationError("UTC timestamp is required")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class FrozenProtocol:
    digest: str
    channels: Mapping[str, str]
    symbols: Mapping[str, str]


def load_frozen_protocol(protocol_path: Path, sidecar_path: Path) -> FrozenProtocol:
    raw = protocol_path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    sidecar = sidecar_path.read_text(encoding="utf-8").strip().split()
    if len(sidecar) != 2 or sidecar[0] != digest or sidecar[1] != protocol_path.name: raise ProtocolError("protocol sidecar mismatch")
    if digest != EXPECTED_PROTOCOL_SHA256: raise ProtocolError("unexpected frozen protocol digest")
    try: data = _loads(raw)
    except (json.JSONDecodeError, ValidationError) as exc: raise ProtocolError("invalid protocol JSON") from exc
    if not isinstance(data, dict): raise ProtocolError("protocol must be an object")
    if data.get("protocol_id") != PROTOCOL_ID or data.get("schema_version") != "1.2.0": raise ProtocolError("unexpected protocol identity")
    if data.get("source_architecture") != "DERIBIT_DVOL_PLUS_BINANCE_SPOT_KLINES" or data.get("assets") != ["BTC", "ETH"]: raise ProtocolError("unexpected source architecture")
    authority = data.get("authority")
    if not isinstance(authority, dict) or not authority or any(value is not False for value in authority.values()): raise ProtocolError("protocol authority must be all false")
    contract = data.get("source_contract", {})
    try:
        channels = contract["deribit_dvol"]["channel"]; symbols = contract["binance_spot_klines"]["symbols"]
        trailing = data["timing_integrity"]["trailing_predictor"]; outcome = data["outcome"]
    except (KeyError, TypeError) as exc: raise ProtocolError("missing source contract") from exc
    if channels != DERIBIT_CHANNELS or symbols != BINANCE_SYMBOLS: raise ProtocolError("unexpected channels or symbols")
    if trailing.get("boundary_closes_required") != 721 or trailing.get("return_count") != 720 or outcome.get("boundary_closes_required") != 169 or outcome.get("return_count") != 168: raise ProtocolError("unexpected observation counts")
    return FrozenProtocol(digest=digest, channels=channels, symbols=symbols)


@dataclass(frozen=True)
class WeekTiming:
    scheduled_monday: date; benchmark_boundary: datetime; formation_target: datetime; formation_acceptance_end: datetime
    first_outcome_boundary: datetime; final_outcome_boundary: datetime; earliest_outcome_retrieval: datetime
    trailing_start_ms: int; trailing_end_ms: int; outcome_start_ms: int; outcome_end_ms: int


def derive_week_timing(scheduled_monday: date, protocol: FrozenProtocol) -> WeekTiming:
    if scheduled_monday.weekday() != 0: raise ValidationError("scheduled date must be Monday")
    b = datetime(scheduled_monday.year, scheduled_monday.month, scheduled_monday.day, tzinfo=UTC)
    f = b + timedelta(days=7, hours=1)
    ms = lambda instant: int(instant.timestamp() * 1000)
    return WeekTiming(scheduled_monday, b, b + timedelta(minutes=5), b + timedelta(minutes=10), b + timedelta(hours=1), f, f + timedelta(seconds=60), ms(b - timedelta(hours=721)), ms(b) - 1, ms(f - timedelta(hours=169)), ms(f) - 1)


def build_deribit_subscription_request(request_id: int = 1) -> bytes:
    if not isinstance(request_id, int) or isinstance(request_id, bool) or request_id < 1: raise ValidationError("request_id must be a positive integer")
    value = {"id": request_id, "jsonrpc": "2.0", "method": "public/subscribe", "params": {"channels": [DERIBIT_CHANNELS["BTC"], DERIBIT_CHANNELS["ETH"]]}}
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class RecordedEvent:
    attempt: int; session_id: str; sequence: int; kind: str; receipt_utc: datetime; receipt_monotonic_ns: int; payload: bytes | None = None; error: str | None = None


def load_recorded_events(path: Path) -> list[RecordedEvent]:
    result=[]
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try: item = _loads(line); payload = item.get("payload")
        except Exception as exc: raise ValidationError(f"invalid fixture line {line_no}") from exc
        if payload is not None and not isinstance(payload, str): raise ValidationError("payload must be text")
        result.append(RecordedEvent(int(item["attempt"]), str(item["session_id"]), int(item["sequence"]), str(item["kind"]), _utc(item["receipt_utc"]), int(item["receipt_monotonic_ns"]), payload.encode() if payload is not None else None, item.get("error")))
    return result


@dataclass(frozen=True)
class AcceptedFormation:
    asset: str; value: float; source_timestamp: datetime; receipt_timestamp: datetime; session_id: str; sequence: int

@dataclass(frozen=True)
class FormationResult:
    disposition: Literal["FORMATION_CAPTURED", "DECLARED_SKIPPED_WEEK", "BLOCKED"]; reason_code: str; accepted: Mapping[str, AcceptedFormation]; retained_events: tuple[RecordedEvent, ...]
    @property
    def completion_timestamp(self) -> datetime | None: return max((x.receipt_timestamp for x in self.accepted.values()), default=None)


def replay_deribit_formation(*, protocol: FrozenProtocol, timing: WeekTiming, events: Iterable[RecordedEvent]) -> FormationResult:
    retained=tuple(events); accepted: dict[str, AcceptedFormation] = {}; sessions: dict[str, tuple[int, int]] = {}; previous_seq=0; previous_mono=-1; previous_utc: datetime | None = None; reconnects=0; resubscribes=0; transport_failed=False; clock_discontinuity=False
    allowed={"CONNECTION_OPEN", "REQUEST_SENT", "PAYLOAD_RECEIVED", "TRANSPORT_ERROR", "CONNECTION_CLOSED"}
    for event in retained:
        if event.kind not in allowed or event.attempt not in (1,2) or event.sequence <= previous_seq: raise ReplayError("invalid attempt, kind, or receipt sequence")
        previous_seq=event.sequence
        if event.receipt_monotonic_ns <= previous_mono or (previous_utc is not None and event.receipt_utc < previous_utc): clock_discontinuity=True
        previous_mono=event.receipt_monotonic_ns; previous_utc=event.receipt_utc
        if event.attempt == 2 and not transport_failed: raise ReplayError("reconnect without transport failure")
        meta=(event.attempt, event.receipt_monotonic_ns)
        if event.session_id in sessions and sessions[event.session_id][0] != event.attempt: raise ReplayError("session identity reused across attempts")
        sessions[event.session_id]=meta
        if event.kind == "CONNECTION_OPEN" and event.attempt == 2:
            reconnects += 1
            if reconnects > 1: raise ReplayError("too many reconnects")
        if event.kind == "REQUEST_SENT" and event.attempt == 2:
            resubscribes += 1
            if resubscribes > 1: raise ReplayError("too many resubscriptions")
        if event.kind == "TRANSPORT_ERROR": transport_failed=True
        if event.kind != "PAYLOAD_RECEIVED" or event.payload is None: continue
        try: obj=_loads(event.payload)
        except Exception: continue
        if not isinstance(obj, dict) or obj.get("method") != "subscription": continue
        params=obj.get("params"); data=params.get("data") if isinstance(params,dict) else None
        if not isinstance(params,dict) or not isinstance(data,dict): continue
        channel=params.get("channel"); asset=next((a for a,c in protocol.channels.items() if c == channel), None)
        if asset is None or data.get("index_name") != ("btc_usd" if asset == "BTC" else "eth_usd"): continue
        stamp=data.get("timestamp"); value=data.get("volatility")
        if not isinstance(stamp,int) or isinstance(stamp,bool) or not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value): continue
        source=datetime.fromtimestamp(stamp / 1000, UTC)
        if not (timing.formation_target <= source <= timing.formation_acceptance_end and timing.formation_target <= event.receipt_utc <= timing.formation_acceptance_end): continue
        if asset not in accepted: accepted[asset]=AcceptedFormation(asset,float(value),source,event.receipt_utc,event.session_id,event.sequence)
    if len(accepted)==2: return FormationResult("FORMATION_CAPTURED", "FORMATION_CAPTURED", accepted, retained)
    if clock_discontinuity or any(e.error for e in retained if e.kind != "TRANSPORT_ERROR"): reason="LOCAL_OPERATIONAL_FAILURE"
    elif transport_failed: reason="TRANSPORT_FAILURE"
    else: reason="SOURCE_NOTIFICATION_ABSENCE"
    return FormationResult("DECLARED_SKIPPED_WEEK", reason, accepted, retained)


@dataclass(frozen=True)
class BinanceRequest:
    asset: str; endpoint: str; parameters: tuple[tuple[str, str | int], ...]


def build_binance_trailing_request(*, asset: Literal["BTC", "ETH"], timing: WeekTiming, protocol: FrozenProtocol) -> BinanceRequest:
    if asset not in BINANCE_SYMBOLS: raise ValidationError("asset must be BTC or ETH")
    return BinanceRequest(asset, BINANCE_KLINES_URL, (("symbol", protocol.symbols[asset]), ("interval", "1h"), ("startTime", timing.trailing_start_ms), ("endTime", timing.trailing_end_ms), ("limit", 721)))


class Clock(Protocol):
    def utc_now(self) -> datetime: ...
    def monotonic_ns(self) -> int: ...

@dataclass(frozen=True)
class RawHttpResponse:
    request: BinanceRequest; request_started_utc: datetime; request_started_monotonic_ns: int; response_completed_utc: datetime; response_completed_monotonic_ns: int; status: int; headers: Mapping[str,str]; body: bytes; body_sha256: str


def fetch_binance_trailing_response(*, session: requests.Session, request: BinanceRequest, clock: Clock) -> RawHttpResponse:
    started_utc, started_mono = clock.utc_now(), clock.monotonic_ns()
    response=session.get(request.endpoint, params=dict(request.parameters), timeout=30)
    completed_utc, completed_mono = clock.utc_now(), clock.monotonic_ns(); body=bytes(response.content)
    result=RawHttpResponse(request,started_utc,started_mono,completed_utc,completed_mono,int(response.status_code),{k:v for k,v in response.headers.items() if k.lower() in {"content-type","date","x-mbx-used-weight-1m"}},body,hashlib.sha256(body).hexdigest())
    if result.status != 200: raise ValidationError(f"Binance status {result.status}")
    return result


@dataclass(frozen=True)
class KlineClose:
    open_time_ms: int; close_time_ms: int; original_close_price: str; canonical_close_price: str; source_row_index: int
@dataclass(frozen=True)
class ValidatedTrailingSeries:
    asset: str; symbol: str; closes: tuple[KlineClose,...]


def parse_and_validate_trailing_klines(*, raw_response_body: bytes, request: BinanceRequest, timing: WeekTiming) -> ValidatedTrailingSeries:
    try: rows=_loads(raw_response_body)
    except Exception as exc: raise ValidationError("malformed kline JSON") from exc
    if not isinstance(rows,list) or len(rows) != 721: raise ValidationError("exactly 721 kline rows required")
    closes=[]
    for index,row in enumerate(rows):
        if not isinstance(row,list) or len(row) <= 6: raise ValidationError(f"invalid kline row {index}")
        opened,close_text,closed=row[0],row[4],row[6]; expected=timing.trailing_start_ms+index*3_600_000
        if not isinstance(opened,int) or isinstance(opened,bool) or opened != expected or not isinstance(closed,int) or isinstance(closed,bool) or closed != opened+3_600_000-1 or closed > timing.trailing_end_ms: raise ValidationError(f"invalid kline timing row {index}")
        if not isinstance(close_text,str): raise ValidationError(f"close is not decimal text row {index}")
        try: decimal=Decimal(close_text)
        except InvalidOperation as exc: raise ValidationError(f"invalid close row {index}") from exc
        if not decimal.is_finite() or decimal <= 0: raise ValidationError(f"invalid close row {index}")
        closes.append(KlineClose(opened,closed,close_text,format(decimal,"f"),index))
    return ValidatedTrailingSeries(request.asset,dict(request.parameters)["symbol"],tuple(closes))


@dataclass(frozen=True)
class TrailingVolatility:
    asset: str; return_count: int; percentage_points: float

def compute_trailing_realized_volatility(series: ValidatedTrailingSeries) -> TrailingVolatility:
    if len(series.closes) != 721: raise ValidationError("721 closes required")
    # Decimal preserves source parsing; float log/stdev is intentionally IEEE-754.
    prices=[float(Decimal(x.canonical_close_price)) for x in series.closes]
    returns=[math.log(current/previous) for previous,current in zip(prices,prices[1:])]
    if len(returns)!=720 or not all(math.isfinite(x) for x in returns): raise ValidationError("invalid return series")
    result=stdev(returns)*math.sqrt(365*24)*100
    if not math.isfinite(result): raise ValidationError("non-finite volatility")
    return TrailingVolatility(series.asset,720,result)


@dataclass(frozen=True)
class SourceEvidence:
    deribit_events: tuple[RecordedEvent,...]; binance_responses: Mapping[str, RawHttpResponse] = field(default_factory=dict)

def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("wb") as out: out.write(content); out.flush(); os.fsync(out.fileno())

def write_offline_week_artifact(*, output_root: Path, protocol: FrozenProtocol, timing: WeekTiming, formation: FormationResult, trailing_series_by_asset: Mapping[str, ValidatedTrailingSeries] | None, trailing_volatility_by_asset: Mapping[str, TrailingVolatility] | None, source_evidence: SourceEvidence, repository_commit: str) -> Path:
    target=output_root/"weeks"/timing.scheduled_monday.isoformat()
    if target.exists(): raise ValidationError("scheduled-week artifact already exists")
    output_root.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=f".{target.name}.",dir=target.parent if target.parent.exists() else output_root))
    try:
        raw_dir=stage/"raw"/"deribit"
        for event in source_evidence.deribit_events:
            if event.payload is not None: _write(raw_dir/f"event-{event.sequence:06d}.payload",event.payload)
        for asset,response in source_evidence.binance_responses.items(): _write(stage/"raw"/"binance"/f"{asset}USDT-trailing.response",response.body)
        if trailing_series_by_asset:
            for asset,series in trailing_series_by_asset.items(): _write(stage/"normalized"/f"{asset}USDT-trailing.json",_canonical({"asset":asset,"symbol":series.symbol,"closes":[asdict(x) for x in series.closes]}))
        status={"status":formation.disposition,"reason_code":formation.reason_code,"scheduled_monday":timing.scheduled_monday.isoformat(),"offline_fixture_replay":True,"scientific_observation":False,"accepted":{a:{"value":v.value,"source_timestamp":v.source_timestamp.isoformat().replace("+00:00","Z"),"receipt_timestamp":v.receipt_timestamp.isoformat().replace("+00:00","Z"),"session_id":v.session_id} for a,v in formation.accepted.items()},"outcome_plan":{"startTime":timing.outcome_start_ms,"endTime":timing.outcome_end_ms,"limit":169,"earliest_request":timing.earliest_outcome_retrieval.isoformat().replace("+00:00","Z")},"trailing_volatility":{a:v.percentage_points for a,v in (trailing_volatility_by_asset or {}).items()}}
        _write(stage/"week_status.json",_canonical(status))
        files=[]
        for path in sorted(x for x in stage.rglob("*") if x.is_file()): files.append({"path":str(path.relative_to(stage)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size})
        manifest={"protocol_sha256":protocol.digest,"repository_commit":repository_commit,"offline_fixture_replay":True,"scientific_observation":False,"network_contacted":False,"analysis_executed":False,"qnty_authority":False,"files":files}
        manifest_bytes=_canonical(manifest); _write(stage/"manifest.json",manifest_bytes); _write(stage/"manifest.sha256",f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n".encode())
        target.parent.mkdir(parents=True,exist_ok=True); os.replace(stage,target)
    except Exception:
        import shutil; shutil.rmtree(stage,ignore_errors=True); raise
    return target

def _main() -> None:
    parser=argparse.ArgumentParser(description="Offline-only DVOL V0 fixture replay")
    sub=parser.add_subparsers(dest="command",required=True); replay=sub.add_parser("replay-fixture")
    for flag in ("protocol","sidecar","deribit-events","output-root"): replay.add_argument("--"+flag,required=True,type=Path)
    replay.add_argument("--scheduled-monday",required=True); replay.add_argument("--binance-btc-response",type=Path); replay.add_argument("--binance-eth-response",type=Path)
    args=parser.parse_args(); protocol=load_frozen_protocol(args.protocol,args.sidecar); timing=derive_week_timing(date.fromisoformat(args.scheduled_monday),protocol); events=tuple(load_recorded_events(args.deribit_events)); formation=replay_deribit_formation(protocol=protocol,timing=timing,events=events)
    series={}; vols={}; responses={}
    if formation.disposition == "FORMATION_CAPTURED":
        supplied={"BTC":args.binance_btc_response,"ETH":args.binance_eth_response}
        if any(x is None for x in supplied.values()): raise SystemExit("Binance responses required for captured formation")
        for asset,path in supplied.items():
            request=build_binance_trailing_request(asset=asset,timing=timing,protocol=protocol); body=path.read_bytes(); responses[asset]=RawHttpResponse(request,timing.formation_target,0,timing.formation_target,0,200,{},body,hashlib.sha256(body).hexdigest()); series[asset]=parse_and_validate_trailing_klines(raw_response_body=body,request=request,timing=timing); vols[asset]=compute_trailing_realized_volatility(series[asset])
    artifact=write_offline_week_artifact(output_root=args.output_root,protocol=protocol,timing=timing,formation=formation,trailing_series_by_asset=series or None,trailing_volatility_by_asset=vols or None,source_evidence=SourceEvidence(events,responses),repository_commit=os.environ.get("QNTYLAB_REPOSITORY_COMMIT","FIXTURE_REPLAY_UNSPECIFIED"))
    manifest=hashlib.sha256((artifact/"manifest.json").read_bytes()).hexdigest(); print(f"status={formation.disposition}\nscheduled_monday={timing.scheduled_monday}\nartifact_path={artifact}\nprotocol_sha256={protocol.digest}\nmanifest_sha256={manifest}\nnetwork_contacted=false\nscientific_observation=false")

if __name__ == "__main__": _main()
