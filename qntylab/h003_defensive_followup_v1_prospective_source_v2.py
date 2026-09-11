"""Operational-source implementation seam for H003 prospective recorder V2.

This module binds first-party Binance Spot public data transport and a local,
append-only evidence writer to the already-qualified H003 recorder foundation.
It does NOT start a scheduler, timer, daemon, or network call by import.  A
separate activation phase must bind this implementation's canonical merge
before real prospective collection starts.

Authority remains paper/shadow research recording only.  No economic verdict,
Qnty acceptance, QntySpot policy, live execution, capital, signing, or
submission authority is created here.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

from . import h003_defensive_followup_v1_prospective_recorder_v2 as recorder
from .h003_defensive_followup_v1_origin_v2 import EXPECTED_ORIGIN_UTC, parse_utc


ROOT = Path(__file__).resolve().parents[1]
RECORDER_FOUNDATION_MERGE_SHA = "f72e38f4275470d921bb97dc1174511827942b81"
RECORDER_FOUNDATION_MERGE_UTC = "2026-09-11T20:20:03Z"
RECORDER_SOURCE_PATH = "qntylab/h003_defensive_followup_v1_prospective_recorder_v2.py"
REST_ENDPOINT = "https://data-api.binance.vision/api/v3/klines"
ARCHIVE_ZIP_URL = "https://data.binance.vision/data/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{year:04d}-{month:02d}.zip"
INTERVAL = "1h"
HOUR_MS = 3_600_000
RECORDING_WINDOW = timedelta(hours=1)
LEDGER_FILENAME = "h003_prospective_v2_events.jsonl"


class SourceBlocked(ValueError):
    """The H003 operational source or persistence boundary fails closed."""


RestFetcher = Callable[..., Sequence[Sequence[Any]]]
ArchiveProvider = Callable[..., tuple[bytes, str] | None]


def canonical_bytes(value: Any) -> bytes:
    return recorder.canonical_bytes(value)


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise SourceBlocked("timezone-aware timestamp required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _instant(value: str | datetime) -> datetime:
    parsed = parse_utc(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise SourceBlocked("timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def _hour(value: datetime) -> datetime:
    value = _instant(value)
    if value.minute or value.second or value.microsecond:
        raise SourceBlocked("hour-aligned timestamp required")
    return value


def validate_source_lineage(root: Path = ROOT) -> dict[str, str]:
    """Bind this seam to the exact qualified recorder foundation on master."""
    recorder.validate_recorder_authority(root)
    try:
        merge_timestamp = __import__("subprocess").check_output(
            ["git", "show", "-s", "--format=%cI", RECORDER_FOUNDATION_MERGE_SHA],
            cwd=root,
            text=True,
        ).strip()
        committed_bytes = __import__("subprocess").check_output(
            ["git", "show", f"{RECORDER_FOUNDATION_MERGE_SHA}:{RECORDER_SOURCE_PATH}"],
            cwd=root,
        )
        __import__("subprocess").run(
            ["git", "merge-base", "--is-ancestor", RECORDER_FOUNDATION_MERGE_SHA, "HEAD"],
            cwd=root,
            check=True,
            stdout=__import__("subprocess").DEVNULL,
            stderr=__import__("subprocess").DEVNULL,
        )
    except (OSError, __import__("subprocess").CalledProcessError) as exc:
        raise SourceBlocked("qualified recorder Git lineage unavailable") from exc
    if parse_utc(merge_timestamp) != parse_utc(RECORDER_FOUNDATION_MERGE_UTC):
        raise SourceBlocked("qualified recorder merge timestamp changed")
    current_bytes = (root / RECORDER_SOURCE_PATH).read_bytes()
    if committed_bytes != current_bytes:
        raise SourceBlocked("qualified recorder source differs from canonical foundation merge")
    return {
        "recorder_foundation_merge_sha": RECORDER_FOUNDATION_MERGE_SHA,
        "recorder_foundation_merge_utc": RECORDER_FOUNDATION_MERGE_UTC,
        "recorder_source_sha256": sha256(current_bytes).hexdigest(),
    }


def latest_completed_logical_close(as_of: datetime) -> datetime:
    """Latest 1h bar logical close that is complete at ``as_of``.

    At exactly HH:00:00, the preceding [HH-1, HH) candle is complete and its
    logical close is HH:00:00.  Open/current/future bars are never admitted.
    """
    now = _instant(as_of)
    return now.replace(minute=0, second=0, microsecond=0)


def request_bounds(*, first_logical_close: datetime, through_logical_close: datetime) -> tuple[int, int]:
    first = _hour(first_logical_close)
    through = _hour(through_logical_close)
    if through < first:
        raise SourceBlocked("empty REST source window")
    return (
        int((first - timedelta(hours=1)).timestamp() * 1000),
        int(through.timestamp() * 1000) - 1,
    )


def default_fetch_klines(
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    interval: str = INTERVAL,
    timeout: float = 30.0,
    opener=urlopen,
) -> list[list[Any]]:
    """Fetch first-party Binance Spot klines, explicitly requesting ms time."""
    if symbol not in recorder.PANEL:
        raise SourceBlocked(f"non-panel symbol rejected: {symbol}")
    if interval != INTERVAL:
        raise SourceBlocked("REST interval must be exactly 1h")
    if start_ms > end_ms:
        raise SourceBlocked("invalid REST request bounds")
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor <= end_ms:
        query = urlencode(
            {
                "symbol": symbol,
                "interval": INTERVAL,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            }
        )
        request = Request(
            f"{REST_ENDPOINT}?{query}",
            headers={
                "User-Agent": "QntyLab-H003-Prospective-Source/2",
                "X-MBX-TIME-UNIT": "MILLISECOND",
            },
        )
        try:
            with opener(request, timeout=timeout) as response:
                if response.status != 200:
                    raise SourceBlocked(f"Binance Spot REST rejected request: HTTP {response.status}")
                page = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise SourceBlocked(f"Binance Spot REST transport failure: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SourceBlocked("Binance Spot REST returned malformed JSON") from exc
        if not isinstance(page, list):
            raise SourceBlocked("Binance Spot REST returned non-array payload")
        if not page:
            break
        rows.extend(page)
        if len(page) < 1000:
            break
        try:
            last_open = int(page[-1][0])
        except (TypeError, ValueError, IndexError) as exc:
            raise SourceBlocked("malformed paginated REST row") from exc
        next_cursor = last_open + HOUR_MS
        if next_cursor <= cursor:
            raise SourceBlocked("REST pagination did not advance")
        cursor = next_cursor
    return rows


def default_archive_provider(
    *,
    symbol: str,
    year: int,
    month: int,
    timeout: float = 120.0,
    opener=urlopen,
) -> tuple[bytes, str] | None:
    """Download one Binance Spot monthly archive and companion CHECKSUM."""
    if symbol not in recorder.PANEL:
        raise SourceBlocked(f"non-panel symbol rejected: {symbol}")
    url = ARCHIVE_ZIP_URL.format(symbol=symbol, year=year, month=month)
    try:
        with opener(Request(url, headers={"User-Agent": "QntyLab-H003-Prospective-Source/2"}), timeout=timeout) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                raise SourceBlocked(f"Spot archive rejected request: HTTP {response.status}")
            zip_bytes = response.read()
        with opener(Request(url + ".CHECKSUM", headers={"User-Agent": "QntyLab-H003-Prospective-Source/2"}), timeout=timeout) as response:
            if response.status != 200:
                raise SourceBlocked("Spot archive CHECKSUM unavailable")
            checksum_text = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise SourceBlocked(f"Spot archive transport failure: {exc}") from exc
    except (URLError, TimeoutError, OSError, UnicodeDecodeError) as exc:
        raise SourceBlocked(f"Spot archive transport failure: {exc}") from exc
    return zip_bytes, checksum_text


def _published_checksum(checksum_text: str) -> str:
    parts = checksum_text.strip().split()
    if not parts or len(parts[0]) != 64:
        raise SourceBlocked("malformed Spot archive CHECKSUM")
    try:
        int(parts[0], 16)
    except ValueError as exc:
        raise SourceBlocked("malformed Spot archive CHECKSUM") from exc
    return parts[0].lower()


def bars_from_authenticated_archive(
    *,
    symbol: str,
    zip_bytes: bytes,
    checksum_text: str,
) -> tuple[recorder.SpotBar, ...]:
    """Verify archive bytes before parsing exact 12-field Spot kline rows."""
    published = _published_checksum(checksum_text)
    if sha256(zip_bytes).hexdigest() != published:
        raise SourceBlocked("Spot archive checksum mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if len(members) != 1:
                raise SourceBlocked("Spot archive must contain exactly one data member")
            payload = archive.read(members[0]).decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise SourceBlocked("malformed Spot archive zip") from exc

    result: list[recorder.SpotBar] = []
    for raw in csv.reader(io.StringIO(payload)):
        if not raw:
            continue
        # Some archive generations include a header; it is metadata, not a row.
        try:
            int(raw[0])
        except ValueError:
            if not result:
                continue
            raise SourceBlocked("unexpected non-data row inside Spot archive")
        try:
            result.append(recorder.spot_bar_from_row(symbol, raw))
        except recorder.RecorderBlocked as exc:
            raise SourceBlocked(f"Spot archive row rejected: {exc}") from exc
    if not result:
        raise SourceBlocked("Spot archive contains no admitted rows")
    return tuple(result)


def completed_archive_months(*, first_logical_close: datetime, through_logical_close: datetime) -> tuple[tuple[int, int], ...]:
    """Months fully before the month containing the requested final close."""
    first_open = (_hour(first_logical_close) - timedelta(hours=1)).astimezone(UTC)
    through = _hour(through_logical_close)
    year, month = first_open.year, first_open.month
    result: list[tuple[int, int]] = []
    while (year, month) < (through.year, through.month):
        result.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(result)


def materialize_bars(
    *,
    through_logical_close: datetime,
    as_of: datetime,
    archive_provider: ArchiveProvider | None = None,
    rest_fetcher: RestFetcher | None = None,
) -> tuple[recorder.SpotBar, ...]:
    """Compose authenticated archives with a first-party REST gap/tail fill.

    Archive rows take precedence.  REST is allowed only to fill uncovered
    required logical closes.  Any open/future row, duplicate after precedence,
    missing hour, malformed row, or panel drift fails closed in the recorder's
    canonical validator.
    """
    validate_source_lineage()
    through = _hour(through_logical_close)
    if through < parse_utc(EXPECTED_ORIGIN_UTC):
        raise SourceBlocked("through close precedes prospective origin")
    latest = latest_completed_logical_close(as_of)
    if through > latest:
        raise SourceBlocked("requested close is not complete at as_of")
    first = recorder.first_required_logical_close()
    archive_provider = archive_provider or default_archive_provider
    rest_fetcher = rest_fetcher or default_fetch_klines
    months = completed_archive_months(first_logical_close=first, through_logical_close=through)
    expected_hours = int((through - first).total_seconds() // 3600) + 1
    required_closes = tuple(first + timedelta(hours=index) for index in range(expected_hours))
    combined: list[recorder.SpotBar] = []

    for symbol in recorder.PANEL:
        covered: set[datetime] = set()
        for year, month in months:
            provided = archive_provider(symbol=symbol, year=year, month=month)
            if provided is None:
                continue
            zip_bytes, checksum_text = provided
            for bar in bars_from_authenticated_archive(
                symbol=symbol,
                zip_bytes=zip_bytes,
                checksum_text=checksum_text,
            ):
                if first <= bar.logical_close_utc <= through:
                    if bar.logical_close_utc in covered:
                        raise SourceBlocked("duplicate archive logical close")
                    combined.append(bar)
                    covered.add(bar.logical_close_utc)

        uncovered = [close for close in required_closes if close not in covered]
        if uncovered:
            start_ms, end_ms = request_bounds(
                first_logical_close=uncovered[0],
                through_logical_close=through,
            )
            for raw_row in rest_fetcher(
                symbol=symbol,
                start_ms=start_ms,
                end_ms=end_ms,
                interval=INTERVAL,
            ):
                try:
                    bar = recorder.spot_bar_from_row(symbol, raw_row)
                except recorder.RecorderBlocked as exc:
                    raise SourceBlocked(f"Spot REST row rejected: {exc}") from exc
                if bar.logical_close_utc > latest or bar.logical_close_utc > through:
                    raise SourceBlocked("REST returned open or future Spot bar")
                if bar.logical_close_utc < uncovered[0]:
                    raise SourceBlocked("REST returned row before requested uncovered range")
                if bar.logical_close_utc in covered:
                    continue
                combined.append(bar)
                covered.add(bar.logical_close_utc)

    try:
        return recorder.validate_bars(combined, through_logical_close=through)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(f"composed Spot source rejected: {exc}") from exc


class EvidenceLedger:
    """Append-only, hash-chained local evidence ledger with fsync on append."""

    def __init__(self, state_dir: Path, *, filename: str = LEDGER_FILENAME):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / filename

    def events(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SourceBlocked("evidence ledger is malformed") from exc
            body = {
                "event_type": event.get("event_type"),
                "previous_event_digest": event.get("previous_event_digest"),
                "payload": event.get("payload"),
            }
            if not isinstance(body["payload"], dict):
                raise SourceBlocked("evidence ledger payload is malformed")
            if body["previous_event_digest"] != previous or event.get("event_digest") != digest(body):
                raise SourceBlocked("evidence ledger chain integrity failure")
            events.append(event)
            previous = event["event_digest"]
        return tuple(events)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        events = self.events()
        previous = events[-1]["event_digest"] if events else None
        body = {
            "event_type": event_type,
            "previous_event_digest": previous,
            "payload": dict(payload),
        }
        event = {**body, "event_digest": digest(body)}
        with self.path.open("ab") as handle:
            handle.write(canonical_bytes(event) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def terminal_block(self) -> dict[str, Any] | None:
        blocked = [event for event in self.events() if event["event_type"] == "RECORDING_BLOCKED"]
        if len(blocked) > 1:
            raise SourceBlocked("multiple terminal recording blocks")
        return blocked[0] if blocked else None

    def recorded(self) -> tuple[dict[str, Any], ...]:
        return tuple(event for event in self.events() if event["event_type"] == "HOUR_RECORDED")

    def next_required_close(self) -> datetime:
        blocked = self.terminal_block()
        if blocked is not None:
            raise SourceBlocked("recording ledger is terminally blocked")
        recorded = self.recorded()
        origin = parse_utc(EXPECTED_ORIGIN_UTC)
        if not recorded:
            return origin
        closes = [_instant(event["payload"]["through_logical_close_utc"]) for event in recorded]
        expected = [origin + timedelta(hours=index) for index in range(len(closes))]
        if closes != expected:
            raise SourceBlocked("recorded close ordering/gap violation")
        return closes[-1] + timedelta(hours=1)

    def receipt_chain_tip(self) -> str | None:
        recorded = self.recorded()
        return None if not recorded else str(recorded[-1]["payload"]["receipt_chain_tip_sha256"])


class OperationalRecorder:
    """One-hour due-window recorder; no scheduler is constructed here."""

    def __init__(
        self,
        state_dir: Path,
        *,
        archive_provider: ArchiveProvider | None = None,
        rest_fetcher: RestFetcher | None = None,
    ):
        self.ledger = EvidenceLedger(state_dir)
        self.archive_provider = archive_provider
        self.rest_fetcher = rest_fetcher

    def status(self, *, now: datetime) -> dict[str, Any]:
        validate_source_lineage()
        if self.ledger.terminal_block() is not None:
            return {
                "state": "BLOCKED_MISSED_RECORDING_WINDOW",
                "next_required_close_utc": None,
                "completed_hour_count": len(self.ledger.recorded()),
                "economic_verdict": "FORBIDDEN",
            }
        due = self.ledger.next_required_close()
        current = _instant(now)
        if current < due:
            due_state = "NOT_DUE"
        elif current >= due + RECORDING_WINDOW:
            due_state = "MISSED_WINDOW"
        else:
            due_state = "DUE"
        return {
            "state": "ARMED_OPERATIONAL_IMPLEMENTATION_NOT_SCHEDULED",
            "next_required_close_utc": _stamp(due),
            "next_due_state": due_state,
            "completed_hour_count": len(self.ledger.recorded()),
            "receipt_chain_tip_sha256": self.ledger.receipt_chain_tip(),
            "economic_verdict": "FORBIDDEN",
            "live_execution": "FORBIDDEN",
        }

    def record_due(self, *, now: datetime) -> dict[str, Any]:
        """Record exactly the next required logical close or fail closed."""
        lineage = validate_source_lineage()
        current = _instant(now)
        if self.ledger.terminal_block() is not None:
            raise SourceBlocked("recording ledger is terminally blocked")
        due = self.ledger.next_required_close()
        if current < due:
            return {
                "state": "NOT_DUE",
                "through_logical_close_utc": _stamp(due),
                "economic_verdict": "FORBIDDEN",
            }
        if current >= due + RECORDING_WINDOW:
            payload = {
                "through_logical_close_utc": _stamp(due),
                "detected_at_utc": _stamp(current),
                "reason": "MISSED_ONE_HOUR_RECORDING_WINDOW",
                "backfill": "FORBIDDEN",
                "economic_verdict": "FORBIDDEN",
                "live_execution": "FORBIDDEN",
            }
            if self.ledger.terminal_block() is None:
                self.ledger.append("RECORDING_BLOCKED", payload)
            return {"state": "BLOCKED_MISSED_RECORDING_WINDOW", **payload}

        bars = materialize_bars(
            through_logical_close=due,
            as_of=current,
            archive_provider=self.archive_provider,
            rest_fetcher=self.rest_fetcher,
        )
        bundle = recorder.build_fixture_bundle(bars, through_logical_close=due)
        current_receipts = [
            item for item in bundle["receipts"] if item["logical_close_utc"] == _stamp(due)
        ]
        if len(current_receipts) != len(recorder.PANEL):
            raise SourceBlocked("current-hour receipt cardinality mismatch")
        if [item["symbol"] for item in current_receipts] != list(recorder.PANEL):
            raise SourceBlocked("current-hour receipt panel order mismatch")
        previous_tip = self.ledger.receipt_chain_tip()
        if current_receipts[0]["previous_receipt_sha256"] != previous_tip:
            raise SourceBlocked("receipt chain does not continue durable ledger tip")

        recorded = self.ledger.recorded()
        if not recorded:
            evidence_bars = list(bars)
            evidence_scope = "BOOTSTRAP_WARMUP_PLUS_ORIGIN"
        else:
            evidence_bars = [bar for bar in bars if bar.logical_close_utc == due]
            evidence_scope = "INCREMENTAL_HOUR_ONLY"
        if len(evidence_bars) != (len(bars) if not recorded else len(recorder.PANEL)):
            raise SourceBlocked("evidence-row scope mismatch")

        evidence_rows = [
            {
                "symbol": bar.symbol,
                "logical_close_utc": _stamp(bar.logical_close_utc),
                "provider_timestamp_unit": bar.provider_timestamp_unit,
                "raw_row": list(bar.raw_row),
                "raw_row_sha256": sha256(canonical_bytes(bar.raw_row)).hexdigest(),
            }
            for bar in evidence_bars
        ]
        payload = {
            "schema_version": "1.0.0",
            "through_logical_close_utc": _stamp(due),
            "recorded_at_utc": _stamp(current),
            "source_lineage": lineage,
            "source_manifest_sha256": bundle["source_manifest"]["source_manifest_sha256"],
            "bundle_sha256": bundle["bundle_sha256"],
            "evidence_scope": evidence_scope,
            "evidence_rows": evidence_rows,
            "current_receipts": current_receipts,
            "receipt_chain_tip_sha256": current_receipts[-1]["receipt_sha256"],
            "economic_performance_metric": "NOT_COMPUTED",
            "interim_economic_verdict": "FORBIDDEN",
            "qnty_acceptance": "NONE",
            "qntyspot_policy": "NONE",
            "live_execution": "FORBIDDEN",
            "capital": "NONE",
            "signing": "NONE",
            "submission": "NONE",
        }
        event = self.ledger.append("HOUR_RECORDED", payload)
        return {
            "state": "RECORDED",
            "event_digest": event["event_digest"],
            **payload,
        }


__all__ = [
    "ARCHIVE_ZIP_URL",
    "EvidenceLedger",
    "OperationalRecorder",
    "RECORDER_FOUNDATION_MERGE_SHA",
    "RECORDER_FOUNDATION_MERGE_UTC",
    "RECORDING_WINDOW",
    "REST_ENDPOINT",
    "SourceBlocked",
    "bars_from_authenticated_archive",
    "completed_archive_months",
    "default_archive_provider",
    "default_fetch_klines",
    "latest_completed_logical_close",
    "materialize_bars",
    "request_bounds",
    "validate_source_lineage",
]
