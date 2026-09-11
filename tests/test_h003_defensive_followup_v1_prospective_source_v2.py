from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import io
import zipfile

import pytest

from qntylab.h003_defensive_followup_v1_origin_v2 import EXPECTED_ORIGIN_UTC, parse_utc
from qntylab.h003_defensive_followup_v1_prospective_recorder_v2 import PANEL, first_required_logical_close
from qntylab.h003_defensive_followup_v1_prospective_source_v2 import (
    OperationalRecorder,
    RECORDER_FOUNDATION_MERGE_SHA,
    RECORDER_FOUNDATION_MERGE_UTC,
    SourceBlocked,
    bars_from_authenticated_archive,
    latest_completed_logical_close,
    materialize_bars,
    request_bounds,
    validate_source_lineage,
)


HOUR_MS = 3_600_000
HOUR_US = 3_600_000_000


def _row(logical_close: datetime, close: float, *, unit: str = "millisecond") -> list[object]:
    opened = logical_close - timedelta(hours=1)
    scale = 1_000 if unit == "millisecond" else 1_000_000
    return [
        int(opened.timestamp() * scale),
        str(close),
        str(close),
        str(close),
        str(close),
        "1.0",
        int(logical_close.timestamp() * scale) - 1,
        "1.0",
        1,
        "0.5",
        "0.5",
        "0",
    ]


def _close_for(symbol: str, index: int) -> float:
    if symbol == "SOLUSDT":
        return 1.0 if index < 144 else 2.0
    if symbol == "BTCUSDT":
        return 3.0 - 0.005 * index
    return 2.0 if index < 144 else 1.0


def _rest_fetcher(*, symbol: str, start_ms: int, end_ms: int, interval: str):
    assert interval == "1h"
    rows = []
    cursor = start_ms
    first = first_required_logical_close()
    while cursor <= end_ms:
        logical_close = datetime.fromtimestamp((cursor + HOUR_MS) / 1000, UTC)
        index = int((logical_close - first).total_seconds() // 3600)
        rows.append(_row(logical_close, _close_for(symbol, index)))
        cursor += HOUR_MS
    return rows


def _future_rest_fetcher(*, symbol: str, start_ms: int, end_ms: int, interval: str):
    rows = list(_rest_fetcher(symbol=symbol, start_ms=start_ms, end_ms=end_ms, interval=interval))
    through = datetime.fromtimestamp((end_ms + 1) / 1000, UTC)
    rows.append(_row(through + timedelta(hours=1), 1.0))
    return rows


def _no_archive(**kwargs):
    return None


def _archive_bytes(rows: list[list[object]]) -> tuple[bytes, str]:
    payload = "\n".join(",".join(str(cell) for cell in row) for row in rows).encode("utf-8") + b"\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("TEST-1h-2026-09.csv", payload)
    zip_bytes = stream.getvalue()
    return zip_bytes, f"{sha256(zip_bytes).hexdigest()}  TEST.zip\n"


def test_source_lineage_binds_exact_canonical_recorder_foundation() -> None:
    lineage = validate_source_lineage()
    assert lineage["recorder_foundation_merge_sha"] == RECORDER_FOUNDATION_MERGE_SHA
    assert lineage["recorder_foundation_merge_utc"] == RECORDER_FOUNDATION_MERGE_UTC
    assert len(lineage["recorder_source_sha256"]) == 64


def test_completed_bar_cutoff_and_rest_bounds_are_exact() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    assert latest_completed_logical_close(origin - timedelta(microseconds=1)) == origin - timedelta(hours=1)
    assert latest_completed_logical_close(origin) == origin
    start_ms, end_ms = request_bounds(
        first_logical_close=first_required_logical_close(),
        through_logical_close=origin,
    )
    assert start_ms == int((first_required_logical_close() - timedelta(hours=1)).timestamp() * 1000)
    assert end_ms == int(origin.timestamp() * 1000) - 1


def test_authenticated_archive_accepts_microseconds_and_rejects_bad_checksum() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    zip_bytes, checksum = _archive_bytes([_row(origin, 123.0, unit="microsecond")])
    bars = bars_from_authenticated_archive(symbol="SOLUSDT", zip_bytes=zip_bytes, checksum_text=checksum)
    assert len(bars) == 1
    assert bars[0].logical_close_utc == origin
    assert bars[0].provider_timestamp_unit == "microsecond"
    with pytest.raises(SourceBlocked, match="checksum mismatch"):
        bars_from_authenticated_archive(
            symbol="SOLUSDT",
            zip_bytes=zip_bytes + b"tamper",
            checksum_text=checksum,
        )


def test_materializer_requires_completed_exact_three_asset_coverage() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    bars = materialize_bars(
        through_logical_close=origin,
        as_of=origin,
        archive_provider=_no_archive,
        rest_fetcher=_rest_fetcher,
    )
    assert len(bars) == 192 * 3
    assert bars[0].logical_close_utc == first_required_logical_close()
    assert bars[-1].logical_close_utc == origin

    with pytest.raises(SourceBlocked, match="not complete"):
        materialize_bars(
            through_logical_close=origin,
            as_of=origin - timedelta(microseconds=1),
            archive_provider=_no_archive,
            rest_fetcher=_rest_fetcher,
        )
    with pytest.raises(SourceBlocked, match="open or future"):
        materialize_bars(
            through_logical_close=origin,
            as_of=origin,
            archive_provider=_no_archive,
            rest_fetcher=_future_rest_fetcher,
        )


def test_operational_writer_persists_bootstrap_then_incremental_evidence_and_chain(tmp_path) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=_rest_fetcher,
    )

    first = operation.record_due(now=origin + timedelta(minutes=5))
    assert first["state"] == "RECORDED"
    assert first["through_logical_close_utc"] == EXPECTED_ORIGIN_UTC
    assert first["evidence_scope"] == "BOOTSTRAP_WARMUP_PLUS_ORIGIN"
    assert len(first["evidence_rows"]) == 192 * 3
    assert len(first["current_receipts"]) == 3
    assert first["current_receipts"][0]["previous_receipt_sha256"] is None
    assert first["economic_performance_metric"] == "NOT_COMPUTED"
    assert first["interim_economic_verdict"] == "FORBIDDEN"
    assert first["live_execution"] == "FORBIDDEN"

    not_due = operation.record_due(now=origin + timedelta(minutes=10))
    assert not_due["state"] == "NOT_DUE"
    assert not_due["through_logical_close_utc"] == (origin + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    second = operation.record_due(now=origin + timedelta(hours=1, minutes=5))
    assert second["state"] == "RECORDED"
    assert second["evidence_scope"] == "INCREMENTAL_HOUR_ONLY"
    assert len(second["evidence_rows"]) == 3
    assert len(second["current_receipts"]) == 3
    assert second["current_receipts"][0]["previous_receipt_sha256"] == first["receipt_chain_tip_sha256"]
    assert second["receipt_chain_tip_sha256"] != first["receipt_chain_tip_sha256"]

    status = operation.status(now=origin + timedelta(hours=1, minutes=10))
    assert status["completed_hour_count"] == 2
    assert status["next_required_close_utc"] == (origin + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert status["economic_verdict"] == "FORBIDDEN"

    # Re-read verifies event-digest and previous-event chain integrity.
    events = operation.ledger.events()
    assert len(events) == 2
    assert events[0]["previous_event_digest"] is None
    assert events[1]["previous_event_digest"] == events[0]["event_digest"]


def test_missed_first_window_blocks_without_backfill(tmp_path) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=_rest_fetcher,
    )
    blocked = operation.record_due(now=origin + timedelta(hours=1))
    assert blocked["state"] == "BLOCKED_MISSED_RECORDING_WINDOW"
    assert blocked["backfill"] == "FORBIDDEN"
    with pytest.raises(SourceBlocked, match="terminally blocked"):
        operation.record_due(now=origin + timedelta(hours=1, minutes=1))
