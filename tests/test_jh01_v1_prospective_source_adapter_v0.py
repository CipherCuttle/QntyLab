"""Unit tests for the unbound JH01 V1 prospective source adapter (Piece A).

Synthetic fixtures only; no network; the real campaign state directory is
never touched.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import Message
from hashlib import sha256
import io
from urllib.error import HTTPError, URLError

import pytest

from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder
from qntylab import jh01_v1_prospective_source_adapter_v0 as adapter

from tests._jh01_v1_prospective_fixtures import (
    FIRST_REQUIRED,
    ORIGIN,
    PANEL,
    REQUIRED_CLOSE_COUNT,
    archive_zip_bytes,
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


class _FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _http_error_opener(code: int):
    def opener(request, timeout=None):
        raise HTTPError(request.full_url, code, "Error", Message(), io.BytesIO(b""))
    return opener


def test_default_archive_provider_http_404_maps_to_absent_month():
    # H2 repair: urlopen raises HTTPError on 404; the default provider must map
    # it to None (absent month) instead of a transport failure.
    assert adapter.default_archive_provider(symbol=PANEL[0], year=2026, month=3, opener=_http_error_opener(404)) is None


def test_default_archive_provider_other_http_errors_fail_closed():
    for code in (403, 500):
        with pytest.raises(adapter.SourceAdapterBlocked, match="archive transport failure"):
            adapter.default_archive_provider(symbol=PANEL[0], year=2026, month=3, opener=_http_error_opener(code))


def test_default_archive_provider_url_error_fails_closed():
    def opener(request, timeout=None):
        raise URLError("connection refused")
    with pytest.raises(adapter.SourceAdapterBlocked, match="archive transport failure"):
        adapter.default_archive_provider(symbol=PANEL[0], year=2026, month=3, opener=opener)


def test_default_archive_provider_success_path_returns_zip_and_checksum():
    zip_bytes, checksum_text = archive_zip_bytes(PANEL[0], 2026, 3)

    def opener(request, timeout=None):
        payload = zip_bytes if str(request.full_url).endswith(".zip") else checksum_text.encode("utf-8")
        return _FakeResponse(payload)

    provided = adapter.default_archive_provider(symbol=PANEL[0], year=2026, month=3, opener=opener)
    assert provided == (zip_bytes, checksum_text)


def test_absent_archive_via_http_404_composition_succeeds_through_rest_tail():
    # Designed resilience chain: every monthly archive 404s -> provider returns
    # None -> the REST tail covers the entire required window -> frozen
    # validate_bars admits the composed bar set.
    def provider(*, symbol: str, year: int, month: int):
        return adapter.default_archive_provider(symbol=symbol, year=year, month=month, opener=_http_error_opener(404))

    def full_window_fetch(*, symbol: str, start_ms: int, end_ms: int, interval: str):
        index = PANEL.index(symbol)
        rows = []
        close = FIRST_REQUIRED
        while close <= ORIGIN:
            open_ms = int((close - timedelta(hours=1)).timestamp() * 1000)
            if start_ms <= open_ms <= end_ms:
                rows.append(kline_row(close, index))
            close += timedelta(hours=1)
        return rows

    bars = adapter.materialize_origin_bars(
        origin=ORIGIN,
        first_required_close=FIRST_REQUIRED,
        archive_provider=provider,
        fetch_klines=full_window_fetch,
    )
    assert len(bars) == len(PANEL) * REQUIRED_CLOSE_COUNT
    ordered = recorder.validate_bars(bars, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    assert ordered == bars


def test_cached_archive_provider_reuses_only_digest_verified_entries(tmp_path, monkeypatch):
    zip_bytes, checksum_text = archive_zip_bytes(PANEL[0], 2026, 3)
    downloads: list[tuple[str, int, int]] = []

    def fake_default(*, symbol: str, year: int, month: int):
        downloads.append((symbol, year, month))
        return zip_bytes, checksum_text

    monkeypatch.setattr(adapter, "default_archive_provider", fake_default)
    provider = adapter.cached_archive_provider(tmp_path / "cache")

    first = provider(symbol=PANEL[0], year=2026, month=3)
    assert first == (zip_bytes, checksum_text)
    assert len(downloads) == 1
    assert list((tmp_path / "cache").iterdir()), "verified download was not persisted"

    # Second attempt: served from cache, zero re-downloads.
    second = provider(symbol=PANEL[0], year=2026, month=3)
    assert second == (zip_bytes, checksum_text)
    assert len(downloads) == 1


def test_cached_archive_provider_discards_corrupt_cache_entry(tmp_path, monkeypatch):
    zip_bytes, checksum_text = archive_zip_bytes(PANEL[0], 2026, 3)
    downloads: list[tuple[str, int, int]] = []

    def fake_default(*, symbol: str, year: int, month: int):
        downloads.append((symbol, year, month))
        return zip_bytes, checksum_text

    monkeypatch.setattr(adapter, "default_archive_provider", fake_default)
    provider = adapter.cached_archive_provider(tmp_path / "cache")
    provider(symbol=PANEL[0], year=2026, month=3)

    # Flip one byte inside the cached zip: reuse must be refused and the entry
    # repaired through a fresh authenticated download.
    corrupted = next(path for path in (tmp_path / "cache").iterdir() if path.suffix == ".zip")
    data = bytearray(corrupted.read_bytes())
    data[0] ^= 0xFF
    corrupted.write_bytes(bytes(data))

    result = provider(symbol=PANEL[0], year=2026, month=3)
    assert result == (zip_bytes, checksum_text)
    assert len(downloads) == 2
    assert corrupted.read_bytes() == zip_bytes


def test_cached_archive_provider_never_persists_unverified_download(tmp_path, monkeypatch):
    bad_bytes = b"unverified-bytes"
    bogus_checksum = f"{'0' * 64}  {PANEL[0]}-1h-2026-03.zip"
    downloads: list[tuple[str, int, int]] = []

    def fake_default(*, symbol: str, year: int, month: int):
        downloads.append((symbol, year, month))
        return bad_bytes, bogus_checksum

    monkeypatch.setattr(adapter, "default_archive_provider", fake_default)
    provider = adapter.cached_archive_provider(tmp_path / "cache")

    # Digest-unverifiable download is passed through unchanged (the frozen
    # archive admission fails closed downstream) but never persisted.
    assert provider(symbol=PANEL[0], year=2026, month=3) == (bad_bytes, bogus_checksum)
    assert list((tmp_path / "cache").iterdir()) == []


def test_cached_archive_provider_passes_absent_month_through_without_caching(tmp_path, monkeypatch):
    downloads: list[tuple[str, int, int]] = []

    def fake_default(*, symbol: str, year: int, month: int):
        downloads.append((symbol, year, month))
        return None

    monkeypatch.setattr(adapter, "default_archive_provider", fake_default)
    provider = adapter.cached_archive_provider(tmp_path / "cache")

    assert provider(symbol=PANEL[0], year=2026, month=3) is None
    assert list((tmp_path / "cache").iterdir()) == []
    # Absent months are not negatively cached: the next attempt re-probes.
    assert provider(symbol=PANEL[0], year=2026, month=3) is None
    assert len(downloads) == 2


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
