"""Operational-source implementation seam for H003 prospective recorder V2.

This module binds first-party Binance Spot public data transport and a private,
append-only evidence writer to the already-qualified H003 recorder foundation.
It does NOT start a scheduler, timer, daemon, or network call by import. A
separate activation phase must bind this implementation's canonical merge
before real prospective collection starts.

Authority remains paper/shadow research recording only. No economic verdict,
Qnty acceptance, QntySpot policy, live execution, capital, signing, or
submission authority is created here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import csv
import fcntl
import io
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterator, Mapping, Sequence
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
ARCHIVE_ZIP_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/"
    "{symbol}/1h/{symbol}-1h-{year:04d}-{month:02d}.zip"
)
INTERVAL = "1h"
HOUR_MS = 3_600_000
RECORDING_WINDOW = timedelta(hours=1)
LEDGER_FILENAME = "h003_prospective_v2_events.jsonl"
LOCK_FILENAME = ".h003_prospective_v2.lock"


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
        merge_timestamp = subprocess.check_output(
            ["git", "show", "-s", "--format=%cI", RECORDER_FOUNDATION_MERGE_SHA],
            cwd=root,
            text=True,
        ).strip()
        committed_bytes = subprocess.check_output(
            ["git", "show", f"{RECORDER_FOUNDATION_MERGE_SHA}:{RECORDER_SOURCE_PATH}"],
            cwd=root,
        )
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", RECORDER_FOUNDATION_MERGE_SHA, "HEAD"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
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
    """Return the most recent completed one-hour logical close."""
    now = _instant(as_of)
    return now.replace(minute=0, second=0, microsecond=0)


def request_bounds(
    *,
    first_logical_close: datetime,
    through_logical_close: datetime,
) -> tuple[int, int]:
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
                    raise SourceBlocked(
                        f"Binance Spot REST rejected request: HTTP {response.status}"
                    )
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
        with opener(
            Request(url, headers={"User-Agent": "QntyLab-H003-Prospective-Source/2"}),
            timeout=timeout,
        ) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                raise SourceBlocked(f"Spot archive rejected request: HTTP {response.status}")
            zip_bytes = response.read()
        with opener(
            Request(url + ".CHECKSUM", headers={"User-Agent": "QntyLab-H003-Prospective-Source/2"}),
            timeout=timeout,
        ) as response:
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


def completed_archive_months(
    *,
    first_logical_close: datetime,
    through_logical_close: datetime,
) -> tuple[tuple[int, int], ...]:
    """Months fully before the month containing the requested final close."""
    first_open = _hour(first_logical_close) - timedelta(hours=1)
    through = _hour(through_logical_close)
    year, month = first_open.year, first_open.month
    result: list[tuple[int, int]] = []
    while (year, month) < (through.year, through.month):
        result.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(result)


def _rest_bar_from_row(
    symbol: str,
    raw_row: Sequence[Any],
    *,
    expected_close: datetime | None = None,
) -> recorder.SpotBar:
    try:
        bar = recorder.spot_bar_from_row(symbol, raw_row)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(f"Spot REST row rejected: {exc}") from exc
    if bar.provider_timestamp_unit != "millisecond":
        raise SourceBlocked("Spot REST row must use requested millisecond timestamps")
    if expected_close is not None and bar.logical_close_utc != expected_close:
        raise SourceBlocked("Spot REST row does not match exact requested logical close")
    return bar


def materialize_bars(
    *,
    through_logical_close: datetime,
    as_of: datetime,
    archive_provider: ArchiveProvider | None = None,
    rest_fetcher: RestFetcher | None = None,
) -> tuple[recorder.SpotBar, ...]:
    """Bootstrap exact warmup/origin coverage from archives plus REST tail.

    This full materializer is used only before the first durable H003 hour is
    recorded. After bootstrap, historical source rows are reconstructed from
    the append-only evidence ledger and only the next exact hour is fetched.
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
    months = completed_archive_months(
        first_logical_close=first,
        through_logical_close=through,
    )
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
                bar = _rest_bar_from_row(symbol, raw_row)
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


def _fetch_incremental_hour(
    *,
    logical_close: datetime,
    as_of: datetime,
    rest_fetcher: RestFetcher | None = None,
) -> tuple[recorder.SpotBar, ...]:
    """Fetch exactly one new completed hour for the frozen three-asset panel."""
    due = _hour(logical_close)
    latest = latest_completed_logical_close(as_of)
    if due > latest:
        raise SourceBlocked("requested incremental close is not complete at as_of")
    rest_fetcher = rest_fetcher or default_fetch_klines
    start_ms, end_ms = request_bounds(
        first_logical_close=due,
        through_logical_close=due,
    )
    result: list[recorder.SpotBar] = []
    for symbol in recorder.PANEL:
        rows = list(
            rest_fetcher(
                symbol=symbol,
                start_ms=start_ms,
                end_ms=end_ms,
                interval=INTERVAL,
            )
        )
        if len(rows) != 1:
            raise SourceBlocked(f"incremental Spot source must return exactly one row for {symbol}")
        bar = _rest_bar_from_row(symbol, rows[0], expected_close=due)
        if bar.logical_close_utc > latest:
            raise SourceBlocked("REST returned open or future Spot bar")
        result.append(bar)
    return tuple(result)


class _EvidenceLedger:
    """Private append-only, hash-chained evidence ledger with fsync on append."""

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

    def _append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
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
        reread = self.events()
        if not reread or reread[-1] != event:
            raise SourceBlocked("durable evidence append verification failed")
        return event

    def terminal_block(self) -> dict[str, Any] | None:
        blocked = [event for event in self.events() if event["event_type"] == "RECORDING_BLOCKED"]
        if len(blocked) > 1:
            raise SourceBlocked("multiple terminal recording blocks")
        return blocked[0] if blocked else None

    def recorded(self) -> tuple[dict[str, Any], ...]:
        return tuple(event for event in self.events() if event["event_type"] == "HOUR_RECORDED")

    def next_required_close(self) -> datetime:
        if self.terminal_block() is not None:
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

    def reconstruct_bars(self) -> tuple[recorder.SpotBar, ...]:
        """Rebuild immutable historical source rows only from durable evidence."""
        recorded = self.recorded()
        if not recorded:
            return ()
        origin = parse_utc(EXPECTED_ORIGIN_UTC)
        expected_close = origin
        bars: list[recorder.SpotBar] = []
        for index, event in enumerate(recorded):
            payload = event["payload"]
            through = _instant(payload.get("through_logical_close_utc"))
            if through != expected_close:
                raise SourceBlocked("durable evidence hour ordering/gap violation")
            expected_scope = "BOOTSTRAP_WARMUP_PLUS_ORIGIN" if index == 0 else "INCREMENTAL_HOUR_ONLY"
            if payload.get("evidence_scope") != expected_scope:
                raise SourceBlocked("durable evidence scope violation")
            rows = payload.get("evidence_rows")
            if not isinstance(rows, list):
                raise SourceBlocked("durable evidence rows are malformed")
            expected_rows = recorder.SLOW * len(recorder.PANEL) if index == 0 else len(recorder.PANEL)
            if len(rows) != expected_rows:
                raise SourceBlocked("durable evidence row cardinality mismatch")
            for row in rows:
                if not isinstance(row, dict):
                    raise SourceBlocked("durable evidence row is malformed")
                symbol = row.get("symbol")
                raw_row = row.get("raw_row")
                if symbol not in recorder.PANEL or not isinstance(raw_row, list):
                    raise SourceBlocked("durable evidence row identity is malformed")
                if row.get("raw_row_sha256") != sha256(canonical_bytes(raw_row)).hexdigest():
                    raise SourceBlocked("durable raw-row digest mismatch")
                try:
                    bar = recorder.spot_bar_from_row(symbol, raw_row)
                except recorder.RecorderBlocked as exc:
                    raise SourceBlocked(f"durable Spot row rejected: {exc}") from exc
                if row.get("logical_close_utc") != _stamp(bar.logical_close_utc):
                    raise SourceBlocked("durable logical-close metadata mismatch")
                if row.get("provider_timestamp_unit") != bar.provider_timestamp_unit:
                    raise SourceBlocked("durable timestamp-unit metadata mismatch")
                if index > 0 and bar.logical_close_utc != through:
                    raise SourceBlocked("incremental durable row does not match recorded hour")
                bars.append(bar)
            expected_close += timedelta(hours=1)
        last = _instant(recorded[-1]["payload"]["through_logical_close_utc"])
        try:
            return recorder.validate_bars(bars, through_logical_close=last)
        except recorder.RecorderBlocked as exc:
            raise SourceBlocked(f"durable source reconstruction failed: {exc}") from exc


class OperationalRecorder:
    """One-hour due-window recorder; no scheduler is constructed here."""

    def __init__(
        self,
        state_dir: Path,
        *,
        archive_provider: ArchiveProvider | None = None,
        rest_fetcher: RestFetcher | None = None,
    ):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._ledger = _EvidenceLedger(state_dir)
        self._lock_path = self.state_dir / LOCK_FILENAME
        self.archive_provider = archive_provider
        self.rest_fetcher = rest_fetcher

    @contextmanager
    def _process_lock(self) -> Iterator[None]:
        """Prevent overlapping timer/manual invocations from forking the chain."""
        with self._lock_path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SourceBlocked("another H003 recorder invocation already holds the process lock") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _status_unlocked(self, *, now: datetime) -> dict[str, Any]:
        validate_source_lineage()
        if self._ledger.terminal_block() is not None:
            return {
                "state": "BLOCKED_MISSED_RECORDING_WINDOW",
                "next_required_close_utc": None,
                "completed_hour_count": len(self._ledger.recorded()),
                "economic_verdict": "FORBIDDEN",
            }
        due = self._ledger.next_required_close()
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
            "completed_hour_count": len(self._ledger.recorded()),
            "receipt_chain_tip_sha256": self._ledger.receipt_chain_tip(),
            "economic_verdict": "FORBIDDEN",
            "live_execution": "FORBIDDEN",
        }

    def status(self, *, now: datetime) -> dict[str, Any]:
        with self._process_lock():
            return self._status_unlocked(now=now)

    def verify_persistence(self) -> dict[str, Any]:
        """Read-only verification surface; no append primitive is exposed."""
        with self._process_lock():
            events = self._ledger.events()
            recorded = self._ledger.recorded()
            bars = self._ledger.reconstruct_bars() if recorded else ()
            return {
                "event_count": len(events),
                "recorded_hour_count": len(recorded),
                "durable_bar_count": len(bars),
                "terminal_blocked": self._ledger.terminal_block() is not None,
                "receipt_chain_tip_sha256": self._ledger.receipt_chain_tip(),
                "last_event_digest": events[-1]["event_digest"] if events else None,
            }

    def record_due(self, *, now: datetime) -> dict[str, Any]:
        """Record exactly the next required logical close or fail closed."""
        with self._process_lock():
            return self._record_due_unlocked(now=now)

    def _record_due_unlocked(self, *, now: datetime) -> dict[str, Any]:
        lineage = validate_source_lineage()
        current = _instant(now)
        if self._ledger.terminal_block() is not None:
            raise SourceBlocked("recording ledger is terminally blocked")
        due = self._ledger.next_required_close()
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
            if self._ledger.terminal_block() is None:
                self._ledger._append("RECORDING_BLOCKED", payload)
            return {"state": "BLOCKED_MISSED_RECORDING_WINDOW", **payload}

        recorded = self._ledger.recorded()
        if not recorded:
            bars = materialize_bars(
                through_logical_close=due,
                as_of=current,
                archive_provider=self.archive_provider,
                rest_fetcher=self.rest_fetcher,
            )
            evidence_bars = list(bars)
            evidence_scope = "BOOTSTRAP_WARMUP_PLUS_ORIGIN"
        else:
            historical = self._ledger.reconstruct_bars()
            expected_historical_tip = due - timedelta(hours=1)
            if not historical or max(bar.logical_close_utc for bar in historical) != expected_historical_tip:
                raise SourceBlocked("durable history does not end at prior required close")
            incremental = _fetch_incremental_hour(
                logical_close=due,
                as_of=current,
                rest_fetcher=self.rest_fetcher,
            )
            bars = tuple(historical) + tuple(incremental)
            try:
                bars = recorder.validate_bars(bars, through_logical_close=due)
            except recorder.RecorderBlocked as exc:
                raise SourceBlocked(f"durable-plus-incremental source rejected: {exc}") from exc
            evidence_bars = list(incremental)
            evidence_scope = "INCREMENTAL_HOUR_ONLY"

        bundle = recorder.build_fixture_bundle(bars, through_logical_close=due)
        current_receipts = [
            item for item in bundle["receipts"] if item["logical_close_utc"] == _stamp(due)
        ]
        if len(current_receipts) != len(recorder.PANEL):
            raise SourceBlocked("current-hour receipt cardinality mismatch")
        if [item["symbol"] for item in current_receipts] != list(recorder.PANEL):
            raise SourceBlocked("current-hour receipt panel order mismatch")
        previous_tip = self._ledger.receipt_chain_tip()
        if current_receipts[0]["previous_receipt_sha256"] != previous_tip:
            raise SourceBlocked("receipt chain does not continue durable ledger tip")

        if recorded:
            historical_receipts = [
                item for item in bundle["receipts"] if item["logical_close_utc"] < _stamp(due)
            ]
            persisted_receipts = [
                receipt
                for event in recorded
                for receipt in event["payload"].get("current_receipts", [])
            ]
            if historical_receipts != persisted_receipts:
                raise SourceBlocked("recomputed historical receipts differ from durable evidence")

        expected_evidence_count = (
            recorder.SLOW * len(recorder.PANEL)
            if evidence_scope == "BOOTSTRAP_WARMUP_PLUS_ORIGIN"
            else len(recorder.PANEL)
        )
        if len(evidence_bars) != expected_evidence_count:
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
        event = self._ledger._append("HOUR_RECORDED", payload)
        return {
            "state": "RECORDED",
            "event_digest": event["event_digest"],
            **payload,
        }


__all__ = [
    "ARCHIVE_ZIP_URL",
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
