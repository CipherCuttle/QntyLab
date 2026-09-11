from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import fcntl
import io
import subprocess
import zipfile

import pytest

import qntylab.h003_defensive_followup_v1_prospective_source_v2 as source_module
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
    rows = list(
        _rest_fetcher(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
        )
    )
    through = datetime.fromtimestamp((end_ms + 1) / 1000, UTC)
    rows.append(_row(through + timedelta(hours=1), 1.0))
    return rows


def _no_archive(**kwargs):
    return None


def _archive_bytes(rows: list[list[object]]) -> tuple[bytes, str]:
    payload = (
        "\n".join(",".join(str(cell) for cell in row) for row in rows).encode("utf-8")
        + b"\n"
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("TEST-1h-2026-09.csv", payload)
    zip_bytes = stream.getvalue()
    return zip_bytes, f"{sha256(zip_bytes).hexdigest()}  TEST.zip\n"


@pytest.fixture
def qualification_authority(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace the production validator only inside the test process.

    There is intentionally no shipped constructor flag or alternate production
    code path that can bypass canonical activation.
    """
    context: dict[str, object] = {
        "operation_mode": "SYNTHETIC_QUALIFICATION_ONLY",
        "activation_merge_sha": None,
        "activation_canonicalized_at_utc": None,
        "source_qualification_merge_sha": None,
        "source_implementation_sha256": sha256(
            source_module.Path(source_module.__file__).read_bytes()
        ).hexdigest(),
    }
    monkeypatch.setattr(
        source_module,
        "validate_activation_authority",
        lambda root=source_module.ROOT: dict(context),
    )
    return context


def test_source_lineage_binds_exact_canonical_recorder_foundation() -> None:
    lineage = validate_source_lineage()
    assert lineage["recorder_foundation_merge_sha"] == RECORDER_FOUNDATION_MERGE_SHA
    assert lineage["recorder_foundation_merge_utc"] == RECORDER_FOUNDATION_MERGE_UTC
    assert len(lineage["recorder_source_sha256"]) == 64


def test_completed_bar_cutoff_and_rest_bounds_are_exact() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    assert latest_completed_logical_close(origin - timedelta(microseconds=1)) == (
        origin - timedelta(hours=1)
    )
    assert latest_completed_logical_close(origin) == origin
    start_ms, end_ms = request_bounds(
        first_logical_close=first_required_logical_close(),
        through_logical_close=origin,
    )
    assert start_ms == int(
        (first_required_logical_close() - timedelta(hours=1)).timestamp() * 1000
    )
    assert end_ms == int(origin.timestamp() * 1000) - 1


def test_authenticated_archive_accepts_microseconds_and_rejects_bad_checksum() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    zip_bytes, checksum = _archive_bytes(
        [_row(origin, 123.0, unit="microsecond")]
    )
    bars = bars_from_authenticated_archive(
        symbol="SOLUSDT",
        zip_bytes=zip_bytes,
        checksum_text=checksum,
    )
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


def test_default_operational_entry_points_follow_activation_lifecycle(tmp_path) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    fetch_count = 0

    def counting_fetcher(*, symbol: str, start_ms: int, end_ms: int, interval: str):
        nonlocal fetch_count
        fetch_count += 1
        return _rest_fetcher(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
        )

    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=counting_fetcher,
    )
    canonical = subprocess.check_output(
        [
            "git",
            "log",
            "--first-parent",
            "-1",
            "--format=%H",
            "origin/master",
            "--",
            source_module.ACTIVATION_ARTIFACT_RELATIVE_PATH,
        ],
        cwd=source_module.ROOT,
        text=True,
    ).strip()
    if not canonical:
        with pytest.raises(
            SourceBlocked,
            match="activation artifact required|activation lineage is incomplete",
        ):
            operation.status(now=origin - timedelta(minutes=1))
        with pytest.raises(
            SourceBlocked,
            match="activation artifact required|activation lineage is incomplete",
        ):
            operation.record_due(now=origin - timedelta(minutes=1))
    else:
        status = operation.status(now=origin - timedelta(minutes=1))
        assert status["state"] == "ACTIVE_PROSPECTIVE_SHADOW"
        assert status["operation_mode"] == "CANONICAL_PROSPECTIVE_SHADOW"
        assert status["next_due_state"] == "NOT_DUE"
        result = operation.record_due(now=origin - timedelta(minutes=1))
        assert result["state"] == "NOT_DUE"
        assert result["operation_mode"] == "CANONICAL_PROSPECTIVE_SHADOW"
    assert fetch_count == 0
    assert not (tmp_path / source_module.LEDGER_FILENAME).exists()
    assert "_qualification_mode" not in source_module.OperationalRecorder.__init__.__annotations__


def test_writer_is_private_and_status_surface_is_read_only(
    tmp_path,
    qualification_authority,
) -> None:
    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=_rest_fetcher,
    )
    assert "EvidenceLedger" not in source_module.__all__
    assert not hasattr(source_module, "EvidenceLedger")
    assert not hasattr(operation, "ledger")
    snapshot = operation.verify_persistence()
    assert snapshot["event_count"] == 0
    assert snapshot["recorded_hour_count"] == 0
    assert snapshot["durable_bar_count"] == 0


def test_operational_writer_bootstraps_once_then_fetches_only_new_hour(
    tmp_path,
    qualification_authority,
) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    calls: list[tuple[str, int, int]] = []

    def counting_fetcher(*, symbol: str, start_ms: int, end_ms: int, interval: str):
        calls.append((symbol, start_ms, end_ms))
        return _rest_fetcher(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
        )

    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=counting_fetcher,
    )

    first = operation.record_due(now=origin + timedelta(minutes=5))
    assert first["state"] == "QUALIFICATION_RECORDED"
    assert first["through_logical_close_utc"] == EXPECTED_ORIGIN_UTC
    assert first["operation_mode"] == "SYNTHETIC_QUALIFICATION_ONLY"
    assert first["evidence_scope"] == "BOOTSTRAP_WARMUP_PLUS_ORIGIN"
    assert len(first["evidence_rows"]) == 192 * 3
    assert len(first["current_receipts"]) == 3
    assert first["current_receipts"][0]["previous_receipt_sha256"] is None
    assert len(calls) == 3

    bootstrap_start = int(
        (first_required_logical_close() - timedelta(hours=1)).timestamp() * 1000
    )
    assert all(start_ms == bootstrap_start for _, start_ms, _ in calls)

    not_due = operation.record_due(now=origin + timedelta(minutes=10))
    assert not_due["state"] == "NOT_DUE"
    assert len(calls) == 3

    second = operation.record_due(now=origin + timedelta(hours=1, minutes=5))
    assert second["state"] == "QUALIFICATION_RECORDED"
    assert second["evidence_scope"] == "INCREMENTAL_HOUR_ONLY"
    assert len(second["evidence_rows"]) == 3
    assert len(second["current_receipts"]) == 3
    assert second["current_receipts"][0]["previous_receipt_sha256"] == first[
        "receipt_chain_tip_sha256"
    ]
    assert len(calls) == 6

    expected_incremental_start = int(origin.timestamp() * 1000)
    expected_incremental_end = int(
        (origin + timedelta(hours=1)).timestamp() * 1000
    ) - 1
    for symbol, start_ms, end_ms in calls[-3:]:
        assert symbol in PANEL
        assert start_ms == expected_incremental_start
        assert end_ms == expected_incremental_end

    persistence = operation.verify_persistence()
    assert persistence["event_count"] == 2
    assert persistence["recorded_hour_count"] == 2
    assert persistence["durable_bar_count"] == 193 * 3
    assert persistence["receipt_chain_tip_sha256"] == second[
        "receipt_chain_tip_sha256"
    ]

    status = operation.status(now=origin + timedelta(hours=1, minutes=10))
    assert status["completed_hour_count"] == 2
    assert status["next_required_close_utc"] == (
        origin + timedelta(hours=2)
    ).isoformat().replace("+00:00", "Z")
    assert status["economic_verdict"] == "FORBIDDEN"


def test_incremental_run_never_refetches_or_accepts_revised_history(
    tmp_path,
    qualification_authority,
) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    bootstrap_finished = False

    def history_hostile_fetcher(
        *, symbol: str, start_ms: int, end_ms: int, interval: str
    ):
        nonlocal bootstrap_finished
        origin_open_ms = int(origin.timestamp() * 1000)
        if bootstrap_finished and start_ms < origin_open_ms:
            raise AssertionError("historical source was refetched after durable bootstrap")
        return _rest_fetcher(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
        )

    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=history_hostile_fetcher,
    )
    first = operation.record_due(now=origin + timedelta(minutes=5))
    bootstrap_finished = True
    second = operation.record_due(now=origin + timedelta(hours=1, minutes=5))
    assert first["state"] == second["state"] == "QUALIFICATION_RECORDED"
    assert second["current_receipts"][0]["previous_receipt_sha256"] == first[
        "receipt_chain_tip_sha256"
    ]


def test_overlapping_invocation_fails_closed_on_process_lock(
    tmp_path,
    qualification_authority,
) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=_rest_fetcher,
    )
    lock_path = tmp_path / source_module.LOCK_FILENAME
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SourceBlocked, match="already holds the process lock"):
            operation.status(now=origin)
        with pytest.raises(SourceBlocked, match="already holds the process lock"):
            operation.record_due(now=origin)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_first_ledger_creation_fsyncs_file_and_parent_directory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    qualification_authority,
) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    calls: list[int] = []
    real_fsync = source_module.os.fsync

    def tracking_fsync(fd: int) -> None:
        calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(source_module.os, "fsync", tracking_fsync)
    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=_rest_fetcher,
    )
    operation.record_due(now=origin + timedelta(minutes=5))
    assert len(calls) >= 2


def test_tampered_durable_ledger_fails_integrity_before_next_fetch(
    tmp_path,
    qualification_authority,
) -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    fetch_count = 0

    def counting_fetcher(*, symbol: str, start_ms: int, end_ms: int, interval: str):
        nonlocal fetch_count
        fetch_count += 1
        return _rest_fetcher(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
        )

    operation = OperationalRecorder(
        tmp_path,
        archive_provider=_no_archive,
        rest_fetcher=counting_fetcher,
    )
    operation.record_due(now=origin + timedelta(minutes=5))
    assert fetch_count == 3

    ledger_path = tmp_path / source_module.LEDGER_FILENAME
    raw = ledger_path.read_text(encoding="utf-8")
    ledger_path.write_text(
        raw.replace('"raw_row_sha256":"', '"raw_row_sha256":"0', 1),
        encoding="utf-8",
    )

    with pytest.raises(SourceBlocked, match="chain integrity failure"):
        operation.record_due(now=origin + timedelta(hours=1, minutes=5))
    assert fetch_count == 3


def test_missed_first_window_blocks_without_backfill(
    tmp_path,
    qualification_authority,
) -> None:
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
