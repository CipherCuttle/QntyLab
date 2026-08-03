"""Strict, offline-only fixture replay for the frozen Deribit DVOL V0 protocol.

This module deliberately contains no HTTP or WebSocket client and no live command.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import stdev
from typing import Any, Iterable, Literal, Mapping

EXPECTED_PROTOCOL_SHA256 = "c4510bab86b6cf7e472499f85dfbf603fe802baa73872fb2b392183ccafea323"
PROTOCOL_ID = "qntylab_deribit_dvol_prospective_forecast_v0"
DERIBIT_CHANNELS = {"BTC": "deribit_volatility_index.btc_usd", "ETH": "deribit_volatility_index.eth_usd"}
BINANCE_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
_COMMIT = __import__("re").compile(r"[0-9a-f]{40}\Z")


class ProtocolError(ValueError):
    pass


class ReplayError(ValueError):
    pass


class ValidationError(ValueError):
    pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON value: {value}")


def _loads(raw: bytes | str) -> Any:
    return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValidationError("timestamp must use Z or +00:00")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValidationError("invalid UTC timestamp") from exc
    if result.tzinfo != UTC:
        raise ValidationError("timestamp must be UTC")
    return result


def _int(value: Any, name: str, *, positive: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or (positive and value <= 0):
        raise ValidationError(f"{name} must be a {'positive ' if positive else ''}integer")
    return value


@dataclass(frozen=True)
class FrozenProtocol:
    digest: str
    channels: Mapping[str, str]
    symbols: Mapping[str, str]


def load_frozen_protocol(protocol_path: Path, sidecar_path: Path) -> FrozenProtocol:
    raw = protocol_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = sidecar_path.read_text(encoding="utf-8").strip().split()
    if len(sidecar) != 2 or sidecar != [digest, protocol_path.name]:
        raise ProtocolError("protocol sidecar mismatch")
    if digest != EXPECTED_PROTOCOL_SHA256:
        raise ProtocolError("unexpected frozen protocol digest")
    try:
        data = _loads(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ProtocolError("invalid protocol JSON") from exc
    if not isinstance(data, dict) or data.get("protocol_id") != PROTOCOL_ID or data.get("schema_version") != "1.2.0":
        raise ProtocolError("unexpected protocol identity")
    if data.get("source_architecture") != "DERIBIT_DVOL_PLUS_BINANCE_SPOT_KLINES" or data.get("assets") != ["BTC", "ETH"]:
        raise ProtocolError("unexpected source architecture")
    authority = data.get("authority")
    if not isinstance(authority, dict) or not authority or any(value is not False for value in authority.values()):
        raise ProtocolError("protocol authority must be all false")
    try:
        channels = data["source_contract"]["deribit_dvol"]["channel"]
        symbols = data["source_contract"]["binance_spot_klines"]["symbols"]
    except (KeyError, TypeError) as exc:
        raise ProtocolError("missing source contract") from exc
    if channels != DERIBIT_CHANNELS or symbols != BINANCE_SYMBOLS:
        raise ProtocolError("unexpected channels or symbols")
    return FrozenProtocol(digest, channels, symbols)


@dataclass(frozen=True)
class WeekTiming:
    scheduled_monday: date
    benchmark_boundary: datetime
    formation_target: datetime
    formation_acceptance_end: datetime
    first_outcome_boundary: datetime
    final_outcome_boundary: datetime
    earliest_outcome_retrieval: datetime
    trailing_start_ms: int
    trailing_end_ms: int
    outcome_start_ms: int
    outcome_end_ms: int


def derive_week_timing(scheduled_monday: date, protocol: FrozenProtocol) -> WeekTiming:
    del protocol
    if scheduled_monday.weekday() != 0:
        raise ValidationError("scheduled date must be Monday")
    boundary = datetime(scheduled_monday.year, scheduled_monday.month, scheduled_monday.day, tzinfo=UTC)
    final = boundary + timedelta(days=7, hours=1)
    millis = lambda instant: int(instant.timestamp() * 1000)
    return WeekTiming(scheduled_monday, boundary, boundary + timedelta(minutes=5), boundary + timedelta(minutes=10), boundary + timedelta(hours=1), final, final + timedelta(seconds=60), millis(boundary - timedelta(hours=721)), millis(boundary) - 1, millis(final - timedelta(hours=169)), millis(final) - 1)


def build_deribit_subscription_request(request_id: int = 1) -> bytes:
    _int(request_id, "request_id", positive=True)
    return json.dumps({"id": request_id, "jsonrpc": "2.0", "method": "public/subscribe", "params": {"channels": [DERIBIT_CHANNELS["BTC"], DERIBIT_CHANNELS["ETH"]]}}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class RecordedEvent:
    attempt: int
    session_id: str
    sequence: int
    kind: str
    receipt_utc: datetime
    receipt_monotonic_ns: int
    payload: bytes | None = None
    error: str | None = None


_KINDS = {"CONNECTION_OPEN", "REQUEST_SENT", "PAYLOAD_RECEIVED", "TRANSPORT_ERROR", "CONNECTION_CLOSED"}


def load_recorded_events(path: Path) -> list[RecordedEvent]:
    raw_lines = path.read_bytes().splitlines()
    if not raw_lines:
        raise ValidationError("event fixture is empty")
    result: list[RecordedEvent] = []
    base = {"attempt", "session_id", "sequence", "kind", "receipt_utc", "receipt_monotonic_ns"}
    for line_no, line in enumerate(raw_lines, 1):
        if not line:
            raise ValidationError(f"empty fixture line {line_no}")
        try:
            item = _loads(line)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValidationError(f"invalid fixture line {line_no}") from exc
        if not isinstance(item, dict) or not base <= item.keys() or not item.keys() <= base | {"payload_base64", "error"}:
            raise ValidationError(f"invalid fixture keys at line {line_no}")
        kind = item["kind"]
        if not isinstance(kind, str) or kind not in _KINDS:
            raise ValidationError("invalid event kind")
        payload_key = "payload_base64" in item
        if (kind in {"REQUEST_SENT", "PAYLOAD_RECEIVED"}) != payload_key:
            raise ValidationError("payload representation does not match event kind")
        if kind == "TRANSPORT_ERROR" and (not isinstance(item.get("error"), str) or not item["error"]):
            raise ValidationError("transport error requires text")
        if kind != "TRANSPORT_ERROR" and "error" in item:
            raise ValidationError("error only allowed on transport error")
        if not isinstance(item["session_id"], str) or not item["session_id"]:
            raise ValidationError("session_id must be non-empty text")
        payload = None
        if payload_key:
            encoded = item["payload_base64"]
            if not isinstance(encoded, str):
                raise ValidationError("payload_base64 must be text")
            try:
                payload = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise ValidationError("invalid payload_base64") from exc
        result.append(RecordedEvent(_int(item["attempt"], "attempt", positive=True), item["session_id"], _int(item["sequence"], "sequence", positive=True), kind, _utc(item["receipt_utc"]), _int(item["receipt_monotonic_ns"], "receipt_monotonic_ns", positive=True), payload, item.get("error")))
    return result


@dataclass(frozen=True)
class AcceptedFormation:
    asset: str
    value: float
    source_timestamp: datetime
    receipt_timestamp: datetime
    session_id: str
    sequence: int
    raw_value_token: str


@dataclass(frozen=True)
class FormationResult:
    disposition: Literal["FORMATION_CAPTURED", "DECLARED_SKIPPED_WEEK", "BLOCKED"]
    reason_code: str
    accepted: Mapping[str, AcceptedFormation]
    retained_events: tuple[RecordedEvent, ...]


def _event_index(event: RecordedEvent) -> dict[str, Any]:
    row = {"attempt": event.attempt, "session_id": event.session_id, "sequence": event.sequence, "kind": event.kind, "receipt_utc": event.receipt_utc.isoformat().replace("+00:00", "Z"), "receipt_monotonic_ns": event.receipt_monotonic_ns}
    if event.error is not None:
        row["error"] = event.error
    if event.payload is not None:
        row["payload_path"] = f"raw/deribit/event-{event.sequence:06d}.payload"
        row["payload_sha256"] = hashlib.sha256(event.payload).hexdigest()
    return row


def _notification(event: RecordedEvent, protocol: FrozenProtocol, timing: WeekTiming) -> tuple[str, AcceptedFormation] | None:
    assert event.payload is not None
    try:
        obj = _loads(event.payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ReplayError("INTEGRITY_FAILURE") from exc
    if not isinstance(obj, dict) or obj.get("method") != "subscription":
        return None
    params = obj.get("params")
    data = params.get("data") if isinstance(params, dict) else None
    if not isinstance(params, dict) or not isinstance(data, dict):
        raise ReplayError("SOURCE_DATA_INVALIDITY")
    channel = params.get("channel")
    asset = next((name for name, expected in protocol.channels.items() if expected == channel), None)
    if asset is None:
        return None
    if data.get("index_name") != ("btc_usd" if asset == "BTC" else "eth_usd"):
        raise ReplayError("SOURCE_DATA_INVALIDITY")
    timestamp, value = data.get("timestamp"), data.get("volatility")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool) or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ReplayError("SOURCE_DATA_INVALIDITY")
    try:
        source = datetime.fromtimestamp(timestamp / 1000, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ReplayError("SOURCE_DATA_INVALIDITY") from exc
    if not (timing.formation_target <= source <= timing.formation_acceptance_end and timing.formation_target <= event.receipt_utc <= timing.formation_acceptance_end):
        return None
    return asset, AcceptedFormation(asset, float(value), source, event.receipt_utc, event.session_id, event.sequence, json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def replay_deribit_formation(*, protocol: FrozenProtocol, timing: WeekTiming, events: Iterable[RecordedEvent]) -> FormationResult:
    retained = tuple(events)
    accepted: dict[str, AcceptedFormation] = {}
    previous_sequence = 0
    previous_mono = 0
    previous_utc: datetime | None = None
    state = "START"
    current_attempt = 0
    current_session: str | None = None
    used_sessions: set[str] = set()
    transport_failed = False
    failure: str | None = None
    clock_bad = False
    for event in retained:
        if event.sequence <= previous_sequence or event.attempt not in (1, 2):
            failure = failure or "INTEGRITY_FAILURE"
            continue
        previous_sequence = event.sequence
        if event.receipt_monotonic_ns <= previous_mono or (previous_utc is not None and event.receipt_utc < previous_utc):
            clock_bad = True
        previous_mono, previous_utc = event.receipt_monotonic_ns, event.receipt_utc
        if event.kind == "CONNECTION_OPEN":
            expected_attempt = 1 if state == "START" else 2 if state == "RETRY" else 0
            if event.attempt != expected_attempt or event.session_id in used_sessions:
                failure = failure or "INTEGRITY_FAILURE"
                continue
            state, current_attempt, current_session = "OPEN", event.attempt, event.session_id
            used_sessions.add(event.session_id)
            continue
        if event.attempt != current_attempt or event.session_id != current_session or state in {"START", "CLOSED"} or (state == "RETRY" and event.kind != "CONNECTION_CLOSED"):
            failure = failure or "INTEGRITY_FAILURE"
            continue
        if event.kind == "REQUEST_SENT":
            if state != "OPEN" or event.payload != build_deribit_subscription_request():
                failure = failure or "INTEGRITY_FAILURE"
            else:
                state = "SUBSCRIBING"
            continue
        if event.kind == "TRANSPORT_ERROR":
            if state not in {"OPEN", "SUBSCRIBING", "SUBSCRIBED"}:
                failure = failure or "INTEGRITY_FAILURE"
            else:
                transport_failed, state = True, "RETRY"
            continue
        if event.kind == "CONNECTION_CLOSED":
            if state not in {"OPEN", "SUBSCRIBING", "SUBSCRIBED", "RETRY"}:
                failure = failure or "INTEGRITY_FAILURE"
            else:
                state = "CLOSED" if state != "RETRY" else "RETRY"
            continue
        if event.kind != "PAYLOAD_RECEIVED" or event.payload is None:
            failure = failure or "INTEGRITY_FAILURE"
            continue
        if state == "SUBSCRIBING":
            try:
                acknowledgement = _loads(event.payload)
            except (json.JSONDecodeError, ValidationError):
                failure = failure or "INTEGRITY_FAILURE"
                continue
            if acknowledgement != {"id": 1, "jsonrpc": "2.0", "result": []}:
                failure = failure or "INTEGRITY_FAILURE"
            else:
                state = "SUBSCRIBED"
            continue
        if state != "SUBSCRIBED":
            failure = failure or "INTEGRITY_FAILURE"
            continue
        try:
            parsed = _notification(event, protocol, timing)
        except ReplayError as exc:
            failure = failure or str(exc)
            continue
        if parsed is not None and parsed[0] not in accepted:
            accepted[parsed[0]] = parsed[1]
    if failure is not None:
        return FormationResult("BLOCKED", failure, accepted, retained)
    if clock_bad:
        return FormationResult("DECLARED_SKIPPED_WEEK", "LOCAL_OPERATIONAL_FAILURE", accepted, retained)
    if len(accepted) == 2:
        return FormationResult("FORMATION_CAPTURED", "FORMATION_CAPTURED", accepted, retained)
    return FormationResult("DECLARED_SKIPPED_WEEK", "TRANSPORT_FAILURE" if transport_failed else "SOURCE_NOTIFICATION_ABSENCE", accepted, retained)


@dataclass(frozen=True)
class BinanceRequest:
    asset: str
    endpoint: str
    parameters: tuple[tuple[str, str | int], ...]


def build_binance_trailing_request(*, asset: Literal["BTC", "ETH"], timing: WeekTiming, protocol: FrozenProtocol) -> BinanceRequest:
    if asset not in BINANCE_SYMBOLS:
        raise ValidationError("asset must be BTC or ETH")
    return BinanceRequest(asset, BINANCE_KLINES_URL, (("symbol", protocol.symbols[asset]), ("interval", "1h"), ("startTime", timing.trailing_start_ms), ("endTime", timing.trailing_end_ms), ("limit", 721)))


def _validate_request(request: BinanceRequest, timing: WeekTiming) -> None:
    if request.asset not in BINANCE_SYMBOLS or request.endpoint != BINANCE_KLINES_URL:
        raise ValidationError("wrong Binance request identity")
    expected = (("symbol", BINANCE_SYMBOLS[request.asset]), ("interval", "1h"), ("startTime", timing.trailing_start_ms), ("endTime", timing.trailing_end_ms), ("limit", 721))
    if request.parameters != expected:
        raise ValidationError("wrong Binance request parameters")


@dataclass(frozen=True)
class RawHttpResponse:
    request: BinanceRequest
    request_started_utc: datetime
    request_started_monotonic_ns: int
    response_completed_utc: datetime
    response_completed_monotonic_ns: int
    status: int
    headers: Mapping[str, str]
    body: bytes
    body_sha256: str


@dataclass(frozen=True)
class KlineClose:
    open_time_ms: int
    close_time_ms: int
    original_close_price: str
    canonical_close_price: str
    source_row_index: int


@dataclass(frozen=True)
class ValidatedTrailingSeries:
    asset: str
    symbol: str
    closes: tuple[KlineClose, ...]


def parse_and_validate_trailing_klines(*, raw_response_body: bytes, request: BinanceRequest, timing: WeekTiming) -> ValidatedTrailingSeries:
    _validate_request(request, timing)
    try:
        rows = _loads(raw_response_body)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValidationError("malformed kline JSON") from exc
    if not isinstance(rows, list) or len(rows) != 721:
        raise ValidationError("exactly 721 kline rows required")
    closes: list[KlineClose] = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < 7:
            raise ValidationError(f"invalid kline row {index}")
        opened, close_text, closed = row[0], row[4], row[6]
        expected = timing.trailing_start_ms + index * 3_600_000
        if not isinstance(opened, int) or isinstance(opened, bool) or not isinstance(closed, int) or isinstance(closed, bool) or opened != expected or closed != opened + 3_600_000 - 1 or closed > timing.trailing_end_ms:
            raise ValidationError(f"invalid kline timing row {index}")
        if not isinstance(close_text, str) or not close_text or "e" in close_text.lower():
            raise ValidationError(f"invalid close row {index}")
        try:
            decimal = Decimal(close_text)
        except InvalidOperation as exc:
            raise ValidationError(f"invalid close row {index}") from exc
        if not decimal.is_finite() or decimal <= 0 or decimal.adjusted() > 300 or decimal.adjusted() < -300:
            raise ValidationError(f"invalid close row {index}")
        closes.append(KlineClose(opened, closed, close_text, format(decimal, "f"), index))
    return ValidatedTrailingSeries(request.asset, BINANCE_SYMBOLS[request.asset], tuple(closes))


@dataclass(frozen=True)
class TrailingVolatility:
    asset: str
    return_count: int
    percentage_points: float


def compute_trailing_realized_volatility(series: ValidatedTrailingSeries) -> TrailingVolatility:
    if len(series.closes) != 721 or series.symbol != BINANCE_SYMBOLS.get(series.asset):
        raise ValidationError("invalid trailing series identity")
    try:
        prices = [float(Decimal(item.canonical_close_price)) for item in series.closes]
        returns = [math.log(current / previous) for previous, current in zip(prices, prices[1:])]
    except (ValueError, OverflowError) as exc:
        raise ValidationError("invalid return series") from exc
    if len(returns) != 720 or not all(math.isfinite(value) for value in returns):
        raise ValidationError("invalid return series")
    result = stdev(returns) * math.sqrt(365 * 24) * 100
    if not math.isfinite(result):
        raise ValidationError("non-finite volatility")
    return TrailingVolatility(series.asset, 720, result)


@dataclass(frozen=True)
class SourceEvidence:
    deribit_events: tuple[RecordedEvent, ...]
    binance_responses: Mapping[str, RawHttpResponse] = field(default_factory=dict)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(content)
        out.flush()
        os.fsync(out.fileno())


def _check_artifact_inputs(formation: FormationResult, series: Mapping[str, ValidatedTrailingSeries] | None, volatility: Mapping[str, TrailingVolatility] | None, evidence: SourceEvidence, repository_commit: str, timing: WeekTiming) -> None:
    if not _COMMIT.fullmatch(repository_commit):
        raise ValidationError("repository commit must be lowercase 40-character SHA")
    if tuple(evidence.deribit_events) != formation.retained_events:
        raise ValidationError("formation and evidence events differ")
    keys = set((series or {}))
    response_keys = set(evidence.binance_responses)
    volatility_keys = set((volatility or {}))
    if formation.disposition == "FORMATION_CAPTURED":
        if set(formation.accepted) != {"BTC", "ETH"} or keys != {"BTC", "ETH"} or response_keys != {"BTC", "ETH"} or volatility_keys != {"BTC", "ETH"}:
            raise ValidationError("captured artifact requires paired evidence")
    elif keys or response_keys or volatility_keys:
        raise ValidationError("non-captured artifact cannot contain Binance evidence")
    for asset, item in (series or {}).items():
        if item.asset != asset or item.symbol != BINANCE_SYMBOLS.get(asset):
            raise ValidationError("series identity mismatch")
    for asset, item in (volatility or {}).items():
        if item.asset != asset:
            raise ValidationError("volatility identity mismatch")
    for asset, item in evidence.binance_responses.items():
        _validate_request(item.request, timing)
        if asset != item.request.asset or not isinstance(item.status, int) or isinstance(item.status, bool) or item.status != 200:
            raise ValidationError("response identity mismatch")
        if not isinstance(item.body, bytes) or item.body_sha256 != hashlib.sha256(item.body).hexdigest():
            raise ValidationError("response identity mismatch")
        if item.request_started_utc.tzinfo != UTC or item.response_completed_utc.tzinfo != UTC or item.request_started_monotonic_ns <= 0 or item.response_completed_monotonic_ns <= item.request_started_monotonic_ns:
            raise ValidationError("response timing mismatch")
        if not isinstance(item.headers, Mapping) or not all(isinstance(key, str) and isinstance(value, str) for key, value in item.headers.items()):
            raise ValidationError("response headers mismatch")


def write_offline_week_artifact(*, output_root: Path, protocol: FrozenProtocol, timing: WeekTiming, formation: FormationResult, trailing_series_by_asset: Mapping[str, ValidatedTrailingSeries] | None, trailing_volatility_by_asset: Mapping[str, TrailingVolatility] | None, source_evidence: SourceEvidence, repository_commit: str) -> Path:
    _check_artifact_inputs(formation, trailing_series_by_asset, trailing_volatility_by_asset, source_evidence, repository_commit, timing)
    target = output_root / "weeks" / timing.scheduled_monday.isoformat()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise ValidationError("scheduled-week artifact already exists") from exc
    try:
        for event in source_evidence.deribit_events:
            if event.payload is not None:
                _write(target / f"raw/deribit/event-{event.sequence:06d}.payload", event.payload)
        _write(target / "raw/deribit/events.jsonl", b"".join(_canonical(_event_index(event)) for event in source_evidence.deribit_events))
        for asset, response in source_evidence.binance_responses.items():
            _write(target / f"raw/binance/{asset}USDT-trailing.response", response.body)
            metadata = {"asset": asset, "endpoint": response.request.endpoint, "parameters": list(response.request.parameters), "request_started_utc": response.request_started_utc.isoformat().replace("+00:00", "Z"), "request_started_monotonic_ns": response.request_started_monotonic_ns, "response_completed_utc": response.response_completed_utc.isoformat().replace("+00:00", "Z"), "response_completed_monotonic_ns": response.response_completed_monotonic_ns, "status": response.status, "headers": dict(response.headers), "body_sha256": response.body_sha256}
            _write(target / f"raw/binance/{asset}USDT-trailing.metadata.json", _canonical(metadata))
        for asset, series in (trailing_series_by_asset or {}).items():
            _write(target / f"normalized/{asset}USDT-trailing.json", _canonical({"asset": asset, "symbol": series.symbol, "closes": [asdict(item) for item in series.closes]}))
        status = {"status": formation.disposition, "reason_code": formation.reason_code, "scheduled_monday": timing.scheduled_monday.isoformat(), "offline_fixture_replay": True, "scientific_observation": False, "accepted": {asset: {"value": item.value, "raw_value_token": item.raw_value_token, "source_timestamp": item.source_timestamp.isoformat().replace("+00:00", "Z"), "receipt_timestamp": item.receipt_timestamp.isoformat().replace("+00:00", "Z"), "session_id": item.session_id, "sequence": item.sequence} for asset, item in formation.accepted.items()}, "trailing_volatility": {asset: item.percentage_points for asset, item in (trailing_volatility_by_asset or {}).items()}}
        _write(target / "week_status.json", _canonical(status))
        files = []
        for path in sorted(item for item in target.rglob("*") if item.is_file()):
            raw = path.read_bytes()
            files.append({"path": str(path.relative_to(target)), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        manifest = {"protocol_sha256": protocol.digest, "repository_commit": repository_commit, "offline_fixture_replay": True, "scientific_observation": False, "network_contacted": False, "analysis_executed": False, "qnty_authority": False, "files": files}
        manifest_bytes = _canonical(manifest)
        _write(target / "manifest.json", manifest_bytes)
        _write(target / "manifest.sha256", f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n".encode())
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _main() -> None:
    parser = argparse.ArgumentParser(description="Offline-only DVOL V0 fixture replay")
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay-fixture")
    for flag in ("protocol", "sidecar", "deribit-events", "output-root"):
        replay.add_argument("--" + flag, required=True, type=Path)
    replay.add_argument("--scheduled-monday", required=True)
    replay.add_argument("--repository-commit", required=True)
    replay.add_argument("--binance-btc-response", type=Path)
    replay.add_argument("--binance-eth-response", type=Path)
    args = parser.parse_args()
    protocol = load_frozen_protocol(args.protocol, args.sidecar)
    timing = derive_week_timing(date.fromisoformat(args.scheduled_monday), protocol)
    events = tuple(load_recorded_events(args.deribit_events))
    formation = replay_deribit_formation(protocol=protocol, timing=timing, events=events)
    supplied = {"BTC": args.binance_btc_response, "ETH": args.binance_eth_response}
    if formation.disposition == "FORMATION_CAPTURED" and any(path is None for path in supplied.values()):
        raise SystemExit("Binance responses required for captured formation")
    if formation.disposition != "FORMATION_CAPTURED" and any(path is not None for path in supplied.values()):
        raise SystemExit("Binance responses forbidden for non-captured formation")
    series: dict[str, ValidatedTrailingSeries] = {}
    volatility: dict[str, TrailingVolatility] = {}
    responses: dict[str, RawHttpResponse] = {}
    for asset, path in supplied.items():
        if path is None:
            continue
        body = path.read_bytes()
        request = build_binance_trailing_request(asset=asset, timing=timing, protocol=protocol)
        responses[asset] = RawHttpResponse(request, timing.formation_target, 1, timing.formation_target, 2, 200, {}, body, hashlib.sha256(body).hexdigest())
        series[asset] = parse_and_validate_trailing_klines(raw_response_body=body, request=request, timing=timing)
        volatility[asset] = compute_trailing_realized_volatility(series[asset])
    artifact = write_offline_week_artifact(output_root=args.output_root, protocol=protocol, timing=timing, formation=formation, trailing_series_by_asset=series or None, trailing_volatility_by_asset=volatility or None, source_evidence=SourceEvidence(events, responses), repository_commit=args.repository_commit)
    manifest = hashlib.sha256((artifact / "manifest.json").read_bytes()).hexdigest()
    print(f"status={formation.disposition}\nreason_code={formation.reason_code}\nscheduled_monday={timing.scheduled_monday}\nartifact_path={artifact}\nrepository_commit={args.repository_commit}\nprotocol_sha256={protocol.digest}\nmanifest_sha256={manifest}\nnetwork_contacted=false\nscientific_observation=false")


if __name__ == "__main__":
    _main()
