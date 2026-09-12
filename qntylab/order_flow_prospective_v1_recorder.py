"""Order Flow Prospective V1 recorder foundation.

Qualification-only implementation for the preregistered signed taker quote
imbalance experiment. Importing this module performs no network, scheduler,
market-data, or persistence action. A later activation phase must separately
authorize real prospective collection.

The recorder freezes the five-symbol Binance USD-M 1h source identity,
logical-close mapping, exhaustive row-validity rules, a one-hour no-backfill
observation window, and deterministic append-only staging.

Local ledger append is staging, not scientific durable ownership. A row is
scientifically anchored only after a separately authorized persistence layer
publishes the exact ledger bytes to an immutable release and independently
restores/verifies those bytes.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


CANDIDATE_ID = "CANDIDATE_ORDER_FLOW_SIGNED_TAKER_QUOTE_IMBALANCE_INCREMENTAL_RETURN_V1"
PANEL = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ENDPOINT_BASE = "https://fapi.binance.com"
ENDPOINT_PATH = "/fapi/v1/klines"
INTERVAL = "1h"
RECORDING_WINDOW = timedelta(hours=1)

FIRST_WARMUP_CLOSE = "2026-09-15T00:00:00Z"
LAST_WARMUP_CLOSE = "2026-09-15T23:00:00Z"
FIRST_ORIGIN = "2026-09-16T00:00:00Z"
LAST_ORIGIN = "2027-01-13T23:00:00Z"
TERMINAL_TAIL_CLOSE = "2027-01-14T00:00:00Z"

LEDGER_FILENAME = "order_flow_prospective_v1_events.jsonl"
LOCK_FILENAME = ".order_flow_prospective_v1.lock"
SCHEMA_VERSION = "1.0.0"

ROW_VALIDITY_RULES = (
    "symbol is one of the five frozen panel symbols",
    "interval is exactly 1h",
    "provider row contains exactly 12 Binance USD-M kline fields",
    "provider open_time equals logical_close minus exactly one hour",
    "provider close_time equals logical_close minus exactly one millisecond",
    "observation is not admitted before the logical close",
    "open and close parse as finite decimals and are strictly positive",
    "quote_asset_volume parses as a finite decimal and is strictly positive",
    "taker_buy_quote_asset_volume parses as a finite decimal and is non-negative",
    "taker_buy_quote_asset_volume does not exceed quote_asset_volume",
    "derived signed_taker_quote_imbalance is finite and lies in [-1,1]",
    "a logical-close batch contains exactly one row for every frozen panel symbol",
    "duplicate or conflicting symbol/logical-close identities fail closed",
    "no discretionary magnitude, outlier, winsorization, or replacement filtering is permitted",
)

NO_AUTHORITY = {
    "market_data_access_authorized": False,
    "scheduler_authorized": False,
    "prospective_activation_authorized": False,
    "scientific_execution_authorized": False,
    "terminal_evaluation_authorized": False,
    "qnty_authorized": False,
    "qntyspot_authorized": False,
    "trading_authorized": False,
    "capital_authority": "NONE",
}


class RecorderBlocked(ValueError):
    """The prospective recorder contract failed closed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def parse_utc(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RecorderBlocked("timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def stamp(value: str | datetime) -> str:
    return parse_utc(value).isoformat().replace("+00:00", "Z")


def hour(value: str | datetime) -> datetime:
    parsed = parse_utc(value)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise RecorderBlocked("logical close must be exactly hour aligned")
    return parsed


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RecorderBlocked(f"{field} is not a decimal") from exc
    if not parsed.is_finite():
        raise RecorderBlocked(f"{field} must be finite")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise RecorderBlocked("non-finite decimal cannot be canonicalized")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def classify_logical_close(logical_close: str | datetime) -> str:
    close = hour(logical_close)
    if hour(FIRST_WARMUP_CLOSE) <= close <= hour(LAST_WARMUP_CLOSE):
        return "CONTROL_WARMUP"
    if hour(FIRST_ORIGIN) <= close <= hour(LAST_ORIGIN):
        return "EVALUATED_SOURCE"
    if close == hour(TERMINAL_TAIL_CLOSE):
        return "TERMINAL_OUTCOME_TAIL"
    raise RecorderBlocked("logical close is outside the frozen prospective grid")


def provider_request_spec(logical_close: str | datetime, *, symbol: str) -> dict[str, Any]:
    close = hour(logical_close)
    classify_logical_close(close)
    if symbol not in PANEL:
        raise RecorderBlocked(f"non-panel symbol rejected: {symbol}")
    provider_open = close - timedelta(hours=1)
    return {
        "endpoint_base": ENDPOINT_BASE,
        "endpoint_path": ENDPOINT_PATH,
        "params": {
            "symbol": symbol,
            "interval": INTERVAL,
            "startTime": int(provider_open.timestamp() * 1000),
            "endTime": int(close.timestamp() * 1000) - 1,
            "limit": 1,
        },
    }


@dataclass(frozen=True)
class NormalizedKline:
    symbol: str
    logical_close_utc: str
    phase: str
    provider_open_time_ms: int
    provider_close_time_ms: int
    open: str
    close: str
    quote_asset_volume: str
    taker_buy_quote_asset_volume: str
    signed_taker_quote_imbalance: str
    raw_row_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": CANDIDATE_ID,
            "symbol": self.symbol,
            "logical_close_utc": self.logical_close_utc,
            "phase": self.phase,
            "provider_open_time_ms": self.provider_open_time_ms,
            "provider_close_time_ms": self.provider_close_time_ms,
            "open": self.open,
            "close": self.close,
            "quote_asset_volume": self.quote_asset_volume,
            "taker_buy_quote_asset_volume": self.taker_buy_quote_asset_volume,
            "signed_taker_quote_imbalance": self.signed_taker_quote_imbalance,
            "raw_row_sha256": self.raw_row_sha256,
        }


def normalize_provider_row(
    *,
    symbol: str,
    logical_close: str | datetime,
    raw_row: Sequence[Any],
    observed_at: str | datetime,
) -> NormalizedKline:
    """Normalize one exact Binance USD-M 1h kline under frozen validity rules."""
    close_boundary = hour(logical_close)
    phase = classify_logical_close(close_boundary)
    observed = parse_utc(observed_at)
    if observed < close_boundary:
        raise RecorderBlocked("provider row observed before logical close completed")
    if symbol not in PANEL:
        raise RecorderBlocked(f"non-panel symbol rejected: {symbol}")
    if len(raw_row) != 12:
        raise RecorderBlocked("provider kline row must contain exactly 12 fields")

    expected_open_ms = int((close_boundary - timedelta(hours=1)).timestamp() * 1000)
    expected_close_ms = int(close_boundary.timestamp() * 1000) - 1
    try:
        provider_open_ms = int(raw_row[0])
        provider_close_ms = int(raw_row[6])
    except (TypeError, ValueError, IndexError) as exc:
        raise RecorderBlocked("provider timestamps are malformed") from exc
    if provider_open_ms != expected_open_ms:
        raise RecorderBlocked("provider open_time does not match logical-close-minus-1h")
    if provider_close_ms != expected_close_ms:
        raise RecorderBlocked("provider close_time does not match logical-close-minus-1ms")

    open_price = _decimal(raw_row[1], field="open")
    close_price = _decimal(raw_row[4], field="close")
    quote_volume = _decimal(raw_row[7], field="quote_asset_volume")
    taker_buy_quote = _decimal(raw_row[10], field="taker_buy_quote_asset_volume")
    if open_price <= 0 or close_price <= 0:
        raise RecorderBlocked("open and close must be strictly positive")
    if quote_volume <= 0:
        raise RecorderBlocked("quote_asset_volume must be strictly positive")
    if taker_buy_quote < 0:
        raise RecorderBlocked("taker_buy_quote_asset_volume must be non-negative")
    if taker_buy_quote > quote_volume:
        raise RecorderBlocked("taker_buy_quote_asset_volume cannot exceed quote_asset_volume")

    imbalance = (Decimal(2) * taker_buy_quote - quote_volume) / quote_volume
    if not imbalance.is_finite() or imbalance < Decimal(-1) or imbalance > Decimal(1):
        raise RecorderBlocked("signed taker quote imbalance outside frozen [-1,1] domain")

    return NormalizedKline(
        symbol=symbol,
        logical_close_utc=stamp(close_boundary),
        phase=phase,
        provider_open_time_ms=provider_open_ms,
        provider_close_time_ms=provider_close_ms,
        open=_decimal_text(open_price),
        close=_decimal_text(close_price),
        quote_asset_volume=_decimal_text(quote_volume),
        taker_buy_quote_asset_volume=_decimal_text(taker_buy_quote),
        signed_taker_quote_imbalance=_decimal_text(imbalance),
        raw_row_sha256=sha256(canonical_bytes(list(raw_row))).hexdigest(),
    )


def normalize_batch(
    *,
    logical_close: str | datetime,
    rows: Mapping[str, Sequence[Any]],
    observed_at: str | datetime,
) -> tuple[NormalizedKline, ...]:
    close_boundary = hour(logical_close)
    if set(rows) != set(PANEL):
        missing = sorted(set(PANEL) - set(rows))
        extra = sorted(set(rows) - set(PANEL))
        raise RecorderBlocked(f"batch must contain exactly frozen panel; missing={missing}, extra={extra}")
    normalized = tuple(
        normalize_provider_row(
            symbol=symbol,
            logical_close=close_boundary,
            raw_row=rows[symbol],
            observed_at=observed_at,
        )
        for symbol in PANEL
    )
    identities = {(row.symbol, row.logical_close_utc) for row in normalized}
    if len(identities) != len(PANEL):
        raise RecorderBlocked("duplicate symbol/logical-close identity")
    return normalized


def synthetic_row(*, symbol: str, logical_close: str | datetime = FIRST_WARMUP_CLOSE) -> list[Any]:
    """Deterministic provider-shaped row used only by qualification tests/workflows."""
    close = hour(logical_close)
    if symbol not in PANEL:
        raise RecorderBlocked(f"non-panel symbol rejected: {symbol}")
    index = PANEL.index(symbol) + 1
    open_ms = int((close - timedelta(hours=1)).timestamp() * 1000)
    close_ms = int(close.timestamp() * 1000) - 1
    open_price = Decimal("100") + Decimal(index)
    close_price = open_price + Decimal("0.25")
    quote_volume = Decimal("1000000") + Decimal(index * 1000)
    taker_quote = quote_volume * (Decimal("0.50") + Decimal(index) / Decimal("100"))
    return [
        open_ms,
        _decimal_text(open_price),
        _decimal_text(open_price + Decimal("1")),
        _decimal_text(open_price - Decimal("1")),
        _decimal_text(close_price),
        "1000",
        close_ms,
        _decimal_text(quote_volume),
        100,
        "500",
        _decimal_text(taker_quote),
        "0",
    ]


def synthetic_batch(logical_close: str | datetime = FIRST_WARMUP_CLOSE) -> dict[str, list[Any]]:
    return {symbol: synthetic_row(symbol=symbol, logical_close=logical_close) for symbol in PANEL}


class EvidenceLedger:
    """Append-only locked local staging ledger; never itself the durable scientific pointer."""

    def __init__(self, state_dir: Path, *, filename: str = LEDGER_FILENAME):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / filename
        self.lock_path = self.state_dir / LOCK_FILENAME

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        with self.lock_path.open("a+b") as lock_handle:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def events(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        result: list[dict[str, Any]] = []
        previous: str | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RecorderBlocked("evidence ledger is malformed") from exc
            body = {
                "event_type": event.get("event_type"),
                "previous_event_digest": event.get("previous_event_digest"),
                "payload": event.get("payload"),
            }
            if not isinstance(body["payload"], dict):
                raise RecorderBlocked("evidence ledger payload is malformed")
            if body["previous_event_digest"] != previous:
                raise RecorderBlocked("evidence ledger previous digest mismatch")
            if event.get("event_digest") != digest(body):
                raise RecorderBlocked("evidence ledger digest mismatch")
            result.append(event)
            previous = event["event_digest"]
        return tuple(result)

    def _append_locked(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        events = self.events()
        previous = events[-1]["event_digest"] if events else None
        body = {"event_type": event_type, "previous_event_digest": previous, "payload": dict(payload)}
        event = {**body, "event_digest": digest(body)}
        created = not self.path.exists()
        with self.path.open("ab") as handle:
            handle.write(canonical_bytes(event) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if created:
            directory_fd = os.open(self.state_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        reread = self.events()
        if not reread or reread[-1] != event:
            raise RecorderBlocked("durable local staging append verification failed")
        return event

    def _event_for_close(self, logical_close_utc: str) -> dict[str, Any] | None:
        matches = [
            event
            for event in self.events()
            if event["payload"].get("logical_close_utc") == logical_close_utc
            and event["event_type"] in {"OBSERVATION_STAGED", "WINDOW_MISSED"}
        ]
        if len(matches) > 1:
            raise RecorderBlocked("multiple terminal states for one logical close")
        return matches[0] if matches else None

    def record_batch(
        self,
        *,
        logical_close: str | datetime,
        rows: Mapping[str, Sequence[Any]],
        observed_at: str | datetime,
    ) -> dict[str, Any]:
        close = hour(logical_close)
        observed = parse_utc(observed_at)
        if observed < close:
            raise RecorderBlocked("observation attempted before logical close")
        if observed >= close + RECORDING_WINDOW:
            raise RecorderBlocked("recording window missed; backfill forbidden")
        normalized = normalize_batch(logical_close=close, rows=rows, observed_at=observed)
        normalized_rows = [row.as_dict() for row in normalized]
        batch_digest = digest(normalized_rows)
        logical_close_utc = stamp(close)

        with self._exclusive_lock():
            existing = self._event_for_close(logical_close_utc)
            if existing is not None:
                if existing["event_type"] != "OBSERVATION_STAGED":
                    raise RecorderBlocked("logical close was already marked missed; backfill forbidden")
                if (
                    existing["payload"].get("batch_digest") == batch_digest
                    and existing["payload"].get("rows") == normalized_rows
                ):
                    return existing
                raise RecorderBlocked("conflicting second observation for logical close")

            return self._append_locked(
                "OBSERVATION_STAGED",
                {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_id": CANDIDATE_ID,
                    "logical_close_utc": logical_close_utc,
                    "phase": classify_logical_close(close),
                    "observed_at_utc": stamp(observed),
                    "recording_deadline_utc": stamp(close + RECORDING_WINDOW),
                    "backfill": "FORBIDDEN",
                    "durable_scientific_state": "OBSERVED_PENDING_ANCHOR",
                    "rows": normalized_rows,
                    "batch_digest": batch_digest,
                },
            )

    def mark_missed(self, *, logical_close: str | datetime, detected_at: str | datetime) -> dict[str, Any]:
        close = hour(logical_close)
        detected = parse_utc(detected_at)
        classify_logical_close(close)
        if detected < close + RECORDING_WINDOW:
            raise RecorderBlocked("cannot mark recording window missed before its deadline")
        logical_close_utc = stamp(close)

        with self._exclusive_lock():
            existing = self._event_for_close(logical_close_utc)
            if existing is not None:
                if existing["event_type"] == "WINDOW_MISSED":
                    return existing
                raise RecorderBlocked("observation already staged for logical close")
            return self._append_locked(
                "WINDOW_MISSED",
                {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_id": CANDIDATE_ID,
                    "logical_close_utc": logical_close_utc,
                    "phase": classify_logical_close(close),
                    "detected_at_utc": stamp(detected),
                    "recording_deadline_utc": stamp(close + RECORDING_WINDOW),
                    "backfill": "FORBIDDEN",
                    "scientific_validity": "INVALID_MISSING_PROSPECTIVE_OBSERVATION",
                    "economic_verdict": "FORBIDDEN",
                },
            )

    def ledger_sha256(self) -> str | None:
        if not self.path.exists():
            return None
        self.events()
        return sha256(self.path.read_bytes()).hexdigest()


def build_synthetic_qualification_ledger(state_dir: Path) -> Path:
    """Build one deterministic synthetic staged observation for persistence qualification."""
    ledger = EvidenceLedger(state_dir)
    close = hour(FIRST_WARMUP_CLOSE)
    ledger.record_batch(
        logical_close=close,
        rows=synthetic_batch(close),
        observed_at=close + timedelta(minutes=7),
    )
    events = ledger.events()
    if len(events) != 1 or events[0]["event_type"] != "OBSERVATION_STAGED":
        raise RecorderBlocked("synthetic qualification ledger construction failed")
    return ledger.path
