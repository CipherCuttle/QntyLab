from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qntylab.h003_defensive_followup_v1_origin_v2 import EXPECTED_ORIGIN_UTC, parse_utc
from qntylab.h003_defensive_followup_v1_prospective_recorder_v2 import (
    NETWORK_TRANSPORT,
    ORIGIN_V2_CANONICAL_MERGE_SHA,
    ORIGIN_V2_CANONICAL_MERGE_UTC,
    PANEL,
    RecorderBlocked,
    build_fixture_bundle,
    first_required_logical_close,
    spot_bar_from_row,
    validate_bars,
    validate_recorder_authority,
)


HOUR_MS = 3_600_000


def _row(logical_close: datetime, close: float) -> list[object]:
    opened = logical_close - timedelta(hours=1)
    open_ms = int(opened.timestamp() * 1000)
    close_ms = int(logical_close.timestamp() * 1000) - 1
    return [
        open_ms,
        str(close),
        str(close),
        str(close),
        str(close),
        "1.0",
        close_ms,
        "1.0",
        1,
        "0.5",
        "0.5",
        "0",
    ]


def _bars(*, through: datetime):
    first = first_required_logical_close()
    count = int((through - first).total_seconds() // 3600) + 1
    result = []
    for symbol in PANEL:
        for index in range(count):
            logical_close = first + timedelta(hours=index)
            if symbol == "SOLUSDT":
                close = 1.0 if index < 144 else 2.0
            elif symbol == "BTCUSDT":
                close = 1.0
            else:
                close = 2.0 if index < 144 else 1.0
            result.append(spot_bar_from_row(symbol, _row(logical_close, close)))
    return result


def test_recorder_authority_is_git_derived_from_canonical_origin_merge() -> None:
    authority = validate_recorder_authority()
    assert authority["origin_v2_canonical_merge_sha"] == ORIGIN_V2_CANONICAL_MERGE_SHA
    assert authority["origin_v2_canonicalized_at_utc"] == ORIGIN_V2_CANONICAL_MERGE_UTC
    assert authority["prospective_origin_utc"] == EXPECTED_ORIGIN_UTC
    assert parse_utc(ORIGIN_V2_CANONICAL_MERGE_UTC) < parse_utc(EXPECTED_ORIGIN_UTC)


def test_spot_row_mapping_requires_exact_completed_1h_contract() -> None:
    logical_close = parse_utc(EXPECTED_ORIGIN_UTC)
    bar = spot_bar_from_row("SOLUSDT", _row(logical_close, 123.45))
    assert bar.logical_close_utc == logical_close
    assert bar.open_time_utc == logical_close - timedelta(hours=1)
    assert bar.close == 123.45

    malformed = _row(logical_close, 123.45)
    malformed[6] = int(malformed[6]) + 1
    with pytest.raises(RecorderBlocked, match="exact 1h interval"):
        spot_bar_from_row("SOLUSDT", malformed)
    with pytest.raises(RecorderBlocked, match="non-panel symbol"):
        spot_bar_from_row("DOGEUSDT", _row(logical_close, 1.0))


def test_source_coverage_is_exact_and_fail_closed() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    through = origin + timedelta(hours=1)
    bars = _bars(through=through)
    ordered = validate_bars(bars, through_logical_close=through)
    expected_per_symbol = 193
    assert len(ordered) == expected_per_symbol * len(PANEL)
    assert ordered[0].logical_close_utc == first_required_logical_close()
    assert ordered[-1].logical_close_utc == through

    missing = list(bars)
    missing.pop(next(index for index, bar in enumerate(missing) if bar.symbol == "BTCUSDT" and bar.logical_close_utc < origin))
    with pytest.raises(RecorderBlocked, match="incomplete source coverage for BTCUSDT"):
        validate_bars(missing, through_logical_close=through)

    future = list(bars)
    future.append(spot_bar_from_row("SOLUSDT", _row(through + timedelta(hours=1), 2.0)))
    with pytest.raises(RecorderBlocked, match="outside exact required warmup/recording window"):
        validate_bars(future, through_logical_close=through)


def test_fixture_bundle_emits_only_chained_shadow_signal_facts() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    through = origin + timedelta(hours=1)
    bundle = build_fixture_bundle(_bars(through=through), through_logical_close=through)

    assert bundle["implementation_scope"] == "FIXTURE_ONLY_NO_NETWORK_NO_SCHEDULER_NO_ECONOMIC_VERDICT"
    assert bundle["network_transport"] == NETWORK_TRANSPORT == "UNBOUND_FIXTURE_ONLY"
    assert bundle["economic_verdict"] == "FORBIDDEN"
    assert bundle["publication"] == "NONE"
    assert bundle["live_execution"] == "FORBIDDEN"

    manifest = bundle["source_manifest"]
    assert manifest["market"] == "Binance Spot"
    assert manifest["ordered_panel"] == list(PANEL)
    assert manifest["first_required_logical_close_utc"] == first_required_logical_close().isoformat().replace("+00:00", "Z")
    assert manifest["through_logical_close_utc"] == through.isoformat().replace("+00:00", "Z")
    assert len(manifest["rows"]) == 193 * 3

    receipts = bundle["receipts"]
    assert len(receipts) == 6
    assert [(item["logical_close_utc"], item["symbol"]) for item in receipts] == [
        (origin.isoformat().replace("+00:00", "Z"), "SOLUSDT"),
        (origin.isoformat().replace("+00:00", "Z"), "BTCUSDT"),
        (origin.isoformat().replace("+00:00", "Z"), "ETHUSDT"),
        (through.isoformat().replace("+00:00", "Z"), "SOLUSDT"),
        (through.isoformat().replace("+00:00", "Z"), "BTCUSDT"),
        (through.isoformat().replace("+00:00", "Z"), "ETHUSDT"),
    ]
    assert receipts[0]["state"] == "LONG"
    assert receipts[1]["state"] == "FLAT"
    assert receipts[2]["state"] == "FLAT"
    assert all(item["economic_performance_metric"] == "NOT_COMPUTED" for item in receipts)
    assert all(item["interim_economic_verdict"] == "FORBIDDEN" for item in receipts)
    assert all(item["live_execution"] == "FORBIDDEN" for item in receipts)

    assert receipts[0]["previous_receipt_sha256"] is None
    for previous, current in zip(receipts, receipts[1:]):
        assert current["previous_receipt_sha256"] == previous["receipt_sha256"]
    assert bundle["receipt_chain_tip_sha256"] == receipts[-1]["receipt_sha256"]

    assert receipts[0]["owned_interval_start_utc"] == EXPECTED_ORIGIN_UTC
    assert receipts[0]["owned_interval_end_utc"] == (origin + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    assert receipts[0]["position_changed_from_previous_prospective_bar"] is False


def test_bundle_is_deterministic_and_chain_can_continue_without_rewriting_history() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    through = origin + timedelta(hours=1)
    bars = _bars(through=through)
    first = build_fixture_bundle(bars, through_logical_close=through)
    second = build_fixture_bundle(bars, through_logical_close=through)
    assert first == second

    previous = "a" * 64
    continued = build_fixture_bundle(
        bars,
        through_logical_close=through,
        previous_chain_sha256=previous,
    )
    assert continued["receipts"][0]["previous_receipt_sha256"] == previous
    assert continued["receipt_chain_tip_sha256"] != first["receipt_chain_tip_sha256"]
