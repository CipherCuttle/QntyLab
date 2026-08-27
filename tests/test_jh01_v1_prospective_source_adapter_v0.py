"""Unit tests for the unbound JH01 V1 prospective source adapter (Piece A).

Synthetic fixtures only; no network; the real campaign state directory is
never touched.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder
from qntylab import jh01_v1_prospective_source_adapter_v0 as adapter

from tests._jh01_v1_prospective_fixtures import (
    FIRST_REQUIRED,
    ORIGIN,
    PANEL,
    REQUIRED_CLOSE_COUNT,
    kline_row,
    synthetic_archive_provider,
    synthetic_fetch_klines,
)


def materialize(*, archive_provider=None, fetch_klines=None):
    return adapter.materialize_origin_bars(
        origin=ORIGIN,
        first_required_close=FIRST_REQUIRED,
        archive_provider=archive_provider or synthetic_archive_provider(),
        fetch_klines=fetch_klines or synthetic_fetch_klines(),
    )


def test_frozen_panel_matches_recorder_constants():
    assert adapter.frozen_panel() == recorder._frozen_panel()
    assert len(adapter.frozen_panel()) == 20


def test_request_bounds_never_extend_beyond_origin_boundary():
    start_ms, end_ms = adapter.request_bounds(first_required_close=FIRST_REQUIRED, origin=ORIGIN)
    assert start_ms == int((FIRST_REQUIRED - timedelta(hours=1)).timestamp() * 1000)
    assert end_ms == int((ORIGIN - timedelta(milliseconds=1)).timestamp() * 1000)


def test_rest_open_bar_rejected():
    open_bar = kline_row(ORIGIN + timedelta(hours=1), 0)  # currently open bar at the origin instant
    with pytest.raises(adapter.SourceAdapterBlocked, match="open or future"):
        adapter.rest_bar_from_row(PANEL[0], open_bar, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_rest_future_close_rejected():
    future = kline_row(ORIGIN + timedelta(hours=25), 0)
    with pytest.raises(adapter.SourceAdapterBlocked, match="open or future"):
        adapter.rest_bar_from_row(PANEL[0], future, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_rest_row_before_first_required_close_rejected():
    early = kline_row(FIRST_REQUIRED - timedelta(hours=1), 0)
    with pytest.raises(adapter.SourceAdapterBlocked, match="before first required close"):
        adapter.rest_bar_from_row(PANEL[0], early, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_non_panel_symbol_rejected():
    row = kline_row(ORIGIN, 0)
    with pytest.raises(adapter.SourceAdapterBlocked, match="non-panel symbol"):
        adapter.rest_bar_from_row("BTCUSDT", row, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_wrong_interval_rejected():
    bad = kline_row(ORIGIN, 0, close_override_ms=int((ORIGIN - timedelta(hours=1)).timestamp() * 1000) + 3_600_000)
    with pytest.raises(adapter.SourceAdapterBlocked, match="exact 1h interval"):
        adapter.rest_bar_from_row(PANEL[0], bad, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_wrong_timestamp_mapping_rejected():
    shifted = kline_row(ORIGIN, 0, open_shift_ms=1000)
    with pytest.raises(adapter.SourceAdapterBlocked, match="hour alignment|logical close"):
        adapter.rest_bar_from_row(PANEL[0], shifted, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_malformed_row_length_rejected():
    row = kline_row(ORIGIN, 0)[:11]
    with pytest.raises(adapter.SourceAdapterBlocked, match="12-field"):
        adapter.rest_bar_from_row(PANEL[0], row, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_rest_requests_are_tail_bounded_and_exact_interval(capture=None):
    captured: list[dict] = []
    bars = materialize(fetch_klines=synthetic_fetch_klines(capture=captured))
    assert bars
    # Archives cover every close through 2026-09-01T00:00Z; REST must only be
    # asked for the not-yet-archived tail and never beyond the origin boundary.
    tail_first_uncovered = datetime(2026, 9, 1, 1, tzinfo=UTC)
    expected_start = int((tail_first_uncovered - timedelta(hours=1)).timestamp() * 1000)
    expected_end = int((ORIGIN - timedelta(milliseconds=1)).timestamp() * 1000)
    assert captured, "REST seam was never consulted"
    for request in captured:
        assert request["symbol"] in PANEL
        assert request["interval"] == "1h"
        assert request["end_ms"] == expected_end
        assert request["start_ms"] == expected_start


def test_composition_is_gap_and_duplicate_free_and_accepted_by_validate_bars():
    bars = materialize()
    assert isinstance(bars, tuple)
    assert len(bars) == len(PANEL) * REQUIRED_CLOSE_COUNT
    keys = {(bar.symbol, bar.logical_close) for bar in bars}
    assert len(keys) == len(bars)
    ordered = recorder.validate_bars(bars, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    assert ordered == bars


def test_missing_panel_symbol_rejected_by_validate_bars():
    victim = PANEL[7]
    base_provider = synthetic_archive_provider()

    def provider_without_victim(*, symbol: str, year: int, month: int):
        if symbol == victim:
            return None
        return base_provider(symbol=symbol, year=year, month=month)

    with pytest.raises(recorder.RecorderBlocked, match="missing source symbol"):
        materialize(archive_provider=provider_without_victim, fetch_klines=synthetic_fetch_klines(omit_symbols=frozenset({victim})))


def test_missing_hour_rejected_as_source_gap():
    victim = PANEL[3]
    dropped_close = datetime(2026, 9, 8, tzinfo=UTC)
    drop_open = int((dropped_close - timedelta(hours=1)).timestamp() * 1000)
    with pytest.raises(recorder.RecorderBlocked, match="source gap"):
        materialize(fetch_klines=synthetic_fetch_klines(drop_opens={victim: {drop_open}}))


def test_absent_archive_month_fails_closed_instead_of_silent_acceptance():
    with pytest.raises(recorder.RecorderBlocked):
        materialize(archive_provider=synthetic_archive_provider(missing_months=frozenset({(2026, 3)})))


def test_manifest_digest_deterministically_regenerated():
    first = materialize()
    second = materialize()
    manifest_one = recorder.source_manifest(first, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    manifest_two = recorder.source_manifest(second, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    assert manifest_one == manifest_two
    sample = first[0]
    expected = sha256(recorder.canonical_bytes(sample.raw_row)).hexdigest()
    assert {"symbol": sample.symbol, "interval": "1h", "raw_row_sha256": expected} == {
        "symbol": manifest_one["rows"][0]["symbol"],
        "interval": manifest_one["rows"][0]["interval"],
        "raw_row_sha256": manifest_one["rows"][0]["raw_row_sha256"],
    }
