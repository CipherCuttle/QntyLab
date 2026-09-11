from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

import qntylab.h003_defensive_followup_v1_prospective_recorder_v2 as recorder_module
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


def _row(logical_close: datetime, close: float, *, unit: str = "millisecond") -> list[object]:
    opened = logical_close - timedelta(hours=1)
    if unit == "millisecond":
        scale = 1_000
    elif unit == "microsecond":
        scale = 1_000_000
    else:
        raise ValueError(unit)
    open_stamp = int(opened.timestamp() * scale)
    close_stamp = int(logical_close.timestamp() * scale) - 1
    return [
        open_stamp,
        str(close),
        str(close),
        str(close),
        str(close),
        "1.0",
        close_stamp,
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
                # Strictly falling history makes MA48 < MA192 by a wide margin;
                # avoid floating equality deciding the synthetic FLAT fixture.
                close = 3.0 - 0.005 * index
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


def test_spot_row_mapping_requires_exact_completed_1h_contract_in_ms_or_us() -> None:
    logical_close = parse_utc(EXPECTED_ORIGIN_UTC)
    millisecond = spot_bar_from_row("SOLUSDT", _row(logical_close, 123.45, unit="millisecond"))
    microsecond = spot_bar_from_row("SOLUSDT", _row(logical_close, 123.45, unit="microsecond"))
    assert millisecond.logical_close_utc == microsecond.logical_close_utc == logical_close
    assert millisecond.open_time_utc == microsecond.open_time_utc == logical_close - timedelta(hours=1)
    assert millisecond.close == microsecond.close == 123.45
    assert millisecond.provider_timestamp_unit == "millisecond"
    assert microsecond.provider_timestamp_unit == "microsecond"
    assert millisecond.raw_row != microsecond.raw_row

    malformed = _row(logical_close, 123.45)
    malformed[6] = int(malformed[6]) + 1
    with pytest.raises(RecorderBlocked, match="not an exact hour in supported ms/us units"):
        spot_bar_from_row("SOLUSDT", malformed)
    with pytest.raises(RecorderBlocked, match="non-panel symbol"):
        spot_bar_from_row("DOGEUSDT", _row(logical_close, 1.0))


def test_source_coverage_is_exact_and_raw_evidence_bound() -> None:
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

    # A caller cannot make the strategy consume one price while the evidence
    # chain hashes a different raw Binance row.
    tampered = list(bars)
    tampered[0] = replace(tampered[0], close=tampered[0].close + 99.0)
    with pytest.raises(RecorderBlocked, match="diverge from raw Binance row evidence"):
        validate_bars(tampered, through_logical_close=through)


def test_fixture_bundle_is_the_only_public_receipt_emitting_authority_path(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "build_signal_receipts" not in recorder_module.__all__
    assert not hasattr(recorder_module, "build_signal_receipts")
    assert "_build_signal_receipts" not in recorder_module.__all__

    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    bars = _bars(through=origin)

    def blocked_authority(*args, **kwargs):
        raise RecorderBlocked("authority gate sentinel")

    monkeypatch.setattr(recorder_module, "validate_recorder_authority", blocked_authority)
    with pytest.raises(RecorderBlocked, match="authority gate sentinel"):
        recorder_module.build_fixture_bundle(bars, through_logical_close=origin)


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
    assert {row["provider_timestamp_unit"] for row in manifest["rows"]} == {"millisecond"}

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
    assert all(item["provider_timestamp_unit"] == "millisecond" for item in receipts)
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
