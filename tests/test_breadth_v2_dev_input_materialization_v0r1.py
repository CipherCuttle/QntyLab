"""Focused V0R1 correction tests: profile-specific funding parent range,
adaptive FUNDING_CARRY backscan, and READY/BLOCKED scientific-cell x
cost-mode accounting.  No strategy execution or outcome path is touched.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from qntylab.binance_um_funding_settlement import HEADER, archive_paths as funding_archive_paths, materialize_from_objects
from qntylab.breadth_v2_dev_inputs import (
    EvidenceCache,
    MarketInputKey,
    build_census,
    discover_funding_carry_start,
    enumerate_market_input_plan,
    funding_parent_start,
)
from qntylab.breadth_v2_input_bundle import InputBundleBlocked, PANEL_ORDER, build_breadth_v2_input_bundle
from qntylab.breadth_v2_runner import FROZEN_PANEL_ORDER, SINGLE_ASSET, SYNCHRONIZED_PANEL

SYMBOL = "TESTUSDT"


class _NoNetworkSession:
    """A session that fails loudly if the test forgot to pre-populate the cache."""

    def get(self, *args, **kwargs):
        raise AssertionError("discovery must not touch the network when the cache is fully pre-populated")


def _zip_bytes(symbol: str, year: int, month: int, rows: list[tuple[int, int, str]]) -> bytes:
    filename = funding_archive_paths(symbol, year, month)["archive_filename"]
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        text = io.StringIO(newline="")
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows([[str(calc_time), str(interval), rate] for calc_time, interval, rate in rows])
        archive.writestr(filename.removesuffix(".zip") + ".csv", text.getvalue())
    return stream.getvalue()


def _checksum_text(symbol: str, year: int, month: int, data: bytes) -> str:
    filename = funding_archive_paths(symbol, year, month)["archive_filename"]
    return f"{hashlib.sha256(data).hexdigest()}  {filename}\n"


def _populate_month(cache: EvidenceCache, symbol: str, year: int, month: int, rows: list[tuple[int, int, str]]) -> None:
    paths = funding_archive_paths(symbol, year, month)
    data = _zip_bytes(symbol, year, month, rows)
    checksum = _checksum_text(symbol, year, month, data)
    cache.put({"kind": "funding_zip", "url": paths["zip_url"], "source_key": paths["source_key"]}, status="AVAILABLE", data=data, suffix=".zip", metadata={"http_status": 200, "suffix": ".zip"})
    cache.put({"kind": "funding_checksum", "url": paths["checksum_url"], "source_key": paths["source_key"] + ".CHECKSUM"}, status="AVAILABLE", data=checksum.encode(), suffix=".CHECKSUM", metadata={"http_status": 200, "suffix": ".CHECKSUM"})


def _populate_absent(cache: EvidenceCache, symbol: str, year: int, month: int) -> None:
    paths = funding_archive_paths(symbol, year, month)
    cache.put({"kind": "funding_zip", "url": paths["zip_url"], "source_key": paths["source_key"]}, status="SOURCE_OBJECT_ABSENT", metadata={"http_status": 404, "suffix": ".zip"})


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_carry_8_exact_events_no_extension_needed(tmp_path):
    cache = EvidenceCache(tmp_path / "evidence")
    t0 = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=24)
    ordinary_start = t0 - timedelta(hours=1)
    # All 8 events fall inside the ordinary [T0-1h, T0] window itself, so no
    # backward extension is required.
    rows = [(_ms(ordinary_start + timedelta(minutes=6 * k)), 8, "0.0001") for k in range(8)]
    _populate_month(cache, SYMBOL, 2024, 6, rows)
    discovered, unresolved = discover_funding_carry_start(cache, _NoNetworkSession(), SYMBOL, t0, t1, required_events=8)
    assert unresolved == []
    assert discovered == ordinary_start.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_carry_168_backscan_irregular_intervals_no_cadence_assumption(tmp_path):
    cache = EvidenceCache(tmp_path / "evidence")
    t0 = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=24)
    # Build 168 events walking backward from T0 with an irregular, non-8h
    # spacing pattern.  If the implementation ever assumed N x 8h, it would
    # both miscount and request the wrong months.
    # Generate a comfortable margin above 168 so the boundary-month floor
    # clip (events before T0-1h in the ordinary month never count) cannot
    # starve the walk into requesting an unpopulated month.
    pattern_hours = [5, 9, 13, 7, 11]
    timestamps = []
    cursor = t0
    for i in range(260):
        cursor = cursor - timedelta(hours=pattern_hours[i % len(pattern_hours)])
        timestamps.append(cursor)
    by_month: dict[tuple[int, int], list[datetime]] = {}
    for ts in timestamps:
        by_month.setdefault((ts.year, ts.month), []).append(ts)
    for (year, month), stamps in by_month.items():
        rows = sorted({(_ms(ts), 8, "0.0001") for ts in stamps})
        _populate_month(cache, SYMBOL, year, month, rows)
    discovered, unresolved = discover_funding_carry_start(cache, _NoNetworkSession(), SYMBOL, t0, t1, required_events=168)
    assert unresolved == []
    discovered_dt = datetime.fromisoformat(discovered.replace("Z", "+00:00"))
    assert discovered_dt <= t0 - timedelta(hours=1)
    assert discovered_dt.day == 1 or discovered_dt == t0 - timedelta(hours=1)


def test_carry_backscan_stops_at_official_history_termination(tmp_path):
    cache = EvidenceCache(tmp_path / "evidence")
    t0 = datetime(2024, 3, 15, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=24)
    ordinary_start = t0 - timedelta(hours=1)
    # Only 3 authenticated events ever existed for this symbol -- all inside
    # the ordinary window itself -- and the archive month before it is
    # genuinely absent (new listing), so extension cannot proceed further.
    rows = [(_ms(ordinary_start + timedelta(minutes=6 * k)), 8, "0.0001") for k in range(3)]
    _populate_month(cache, SYMBOL, 2024, 3, rows)
    _populate_absent(cache, SYMBOL, 2024, 2)
    discovered, unresolved = discover_funding_carry_start(cache, _NoNetworkSession(), SYMBOL, t0, t1, required_events=8)
    assert unresolved == []
    # Discovery must stop at the ordinary month (2024-03) -- the absent
    # 2024-02 object is never included, and no zero-fill/assumed-cadence
    # workaround manufactures the missing history.
    assert discovered == (t0 - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _price_source(symbol: str, timestamp: str) -> dict:
    row = {"timestamp": timestamp, "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}
    csv_text = "timestamp,open,high,low,close,volume\r\n" + ",".join(row[k] for k in ("timestamp", "open", "high", "low", "close", "volume")) + "\r\n"
    raw = csv_text.encode()
    return {"manifest": {"normalized_sha256": hashlib.sha256(raw).hexdigest(), "gap_count": 0, "materializer_contract_version": "TEST", "aggregate_source_receipt_digest": "d" * 64}, "normalized_csv": csv_text}


def _funding_source(symbol: str, event_stamps_ms: list[int]) -> dict:
    events = [{"symbol": symbol, "funding_time_ms": ms, "funding_time_utc": "x", "funding_rate": "0.0001"} for ms in sorted(event_stamps_ms)]
    jsonl = "".join(json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n" for e in events)
    raw = jsonl.encode()
    manifest = {"normalized_sha256": hashlib.sha256(raw).hexdigest(), "coverage_status": "COMPLETE", "materializer_contract_version": "TEST", "archive_aggregate_source_receipt_digest": "d" * 64, "rest_coverage_witness_digest": "d" * 64, "coverage_reconciliation_digest": "d" * 64}
    return {"manifest": manifest, "normalized_jsonl": jsonl}


def test_carry_insufficient_history_blocks_warmup_not_zero_fill():
    t0 = "2024-06-01T00:00:00Z"
    t0_dt = datetime.fromisoformat(t0.replace("Z", "+00:00"))
    funding = _funding_source(PANEL_ORDER[0], [int((t0_dt - timedelta(hours=h)).timestamp() * 1000) for h in (3, 2, 1)])
    price = _price_source(PANEL_ORDER[0], (t0_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    price_sources = {symbol: price for symbol in PANEL_ORDER}
    funding_sources = {symbol: funding for symbol in PANEL_ORDER}
    with pytest.raises(InputBundleBlocked) as exc:
        build_breadth_v2_input_bundle(evaluation_start=t0, evaluation_end=t0, symbols=list(PANEL_ORDER), price_sources=price_sources, funding_sources=funding_sources, family="FUNDING_CARRY", parameters={"funding_window_events": 8})
    assert exc.value.status == "BLOCKED_FUNDING_WARMUP"


def test_profile_isolation_same_symbol_ordinary_ready_carry_blocked():
    t0 = "2024-06-01T00:00:00Z"
    t0_dt = datetime.fromisoformat(t0.replace("Z", "+00:00"))
    funding = _funding_source(PANEL_ORDER[0], [int((t0_dt - timedelta(hours=h)).timestamp() * 1000) for h in (3, 2, 1)])
    price = _price_source(PANEL_ORDER[0], (t0_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ready = build_breadth_v2_input_bundle(evaluation_start=t0, evaluation_end=t0, symbols=[PANEL_ORDER[0]], price_sources={PANEL_ORDER[0]: price}, funding_sources={PANEL_ORDER[0]: funding}, family=None, parameters=None)
    assert ready["status"] == "READY"
    with pytest.raises(InputBundleBlocked) as exc:
        build_breadth_v2_input_bundle(evaluation_start=t0, evaluation_end=t0, symbols=list(PANEL_ORDER), price_sources={s: price for s in PANEL_ORDER}, funding_sources={s: funding for s in PANEL_ORDER}, family="FUNDING_CARRY", parameters={"funding_window_events": 168})
    assert exc.value.status == "BLOCKED_FUNDING_WARMUP"


def test_ordinary_funding_isolated_from_missing_old_month():
    t0 = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
    ordinary_start = t0 - timedelta(hours=1)  # same month as T0, no boundary crossing
    rows = [(_ms(ordinary_start), 8, "0.0001")]
    zip_bytes = _zip_bytes(SYMBOL, 2024, 6, rows)
    objects = {(2024, 6): (zip_bytes, _checksum_text(SYMBOL, 2024, 6, zip_bytes))}
    # No object supplied for any older month (e.g. 60 days earlier) -- the
    # ordinary funding parent must not request it.
    result = materialize_from_objects(SYMBOL, ordinary_start, t0, objects, rest_witness_pages=[[{"symbol": SYMBOL, "fundingTime": _ms(ordinary_start), "fundingRate": "0.0001"}]])
    assert result["status"] == "MATERIALIZED_VERIFIED"
    assert result["manifest"]["coverage_status"] == "COMPLETE"


def test_scientific_cell_arithmetic_doubles_for_two_cost_modes():
    keys = enumerate_market_input_plan()
    single_key = next(k for k in keys if k.execution_unit_type == SINGLE_ASSET)
    panel_key = next(k for k in keys if k.execution_unit_type == SYNCHRONIZED_PANEL)
    rows = []
    for key in keys:
        ready = key in (single_key, panel_key)
        rows.append({**asdict(key), "status": "READY" if ready else "BLOCKED", "evaluation_input_bundle_sha256": ("b" * 64) if ready else None, "blocking_reason": None if ready else "BLOCKED_PRICE_COVERAGE"})
    census = build_census(rows, freeze_commit="2608676b1d353446b00409c63a32b4b6a362c38e")
    assert census["ready_input_records"] == 2
    assert census["ready_mapped_scientific_cells"] == 2 + 40
    assert census["ready_mapped_scientific_cells"] + census["blocked_mapped_scientific_cells"] == 3360
    assert census["ready_mapped_execution_units"] + census["blocked_mapped_execution_units"] == 1992


def test_outcome_guard_no_execution_or_ledger_symbols_imported():
    import qntylab.breadth_v2_dev_inputs as module
    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in ("PortfolioKernel.execute", "prepare_breadth_v2_evaluation", "record_breadth_v2_evaluation", "target_weights"):
        assert forbidden not in source
