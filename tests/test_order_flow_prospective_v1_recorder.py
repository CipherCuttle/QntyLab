from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from qntylab.order_flow_prospective_v1_recorder import (
    CANDIDATE_ID,
    FIRST_ORIGIN,
    FIRST_WARMUP_CLOSE,
    LAST_ORIGIN,
    LAST_WARMUP_CLOSE,
    NO_AUTHORITY,
    PANEL,
    ROW_VALIDITY_RULES,
    TERMINAL_TAIL_CLOSE,
    EvidenceLedger,
    RecorderBlocked,
    classify_logical_close,
    normalize_batch,
    normalize_provider_row,
    provider_request_spec,
    synthetic_batch,
    synthetic_row,
)


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = (
    ROOT
    / "experiments"
    / "research"
    / "qnty_edge_discovery_order_flow_v1"
    / "recorder_qualification.json"
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_frozen_grid_and_provider_request_translation_are_exact() -> None:
    assert classify_logical_close(FIRST_WARMUP_CLOSE) == "CONTROL_WARMUP"
    assert classify_logical_close(LAST_WARMUP_CLOSE) == "CONTROL_WARMUP"
    assert classify_logical_close(FIRST_ORIGIN) == "EVALUATED_SOURCE"
    assert classify_logical_close(LAST_ORIGIN) == "EVALUATED_SOURCE"
    assert classify_logical_close(TERMINAL_TAIL_CLOSE) == "TERMINAL_OUTCOME_TAIL"
    with pytest.raises(RecorderBlocked):
        classify_logical_close("2026-09-14T23:00:00Z")

    close = _utc(FIRST_WARMUP_CLOSE)
    spec = provider_request_spec(close, symbol="BTCUSDT")
    assert spec["endpoint_base"] == "https://fapi.binance.com"
    assert spec["endpoint_path"] == "/fapi/v1/klines"
    assert spec["params"] == {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "startTime": int((close - timedelta(hours=1)).timestamp() * 1000),
        "endTime": int(close.timestamp() * 1000) - 1,
        "limit": 1,
    }


def test_valid_provider_row_normalizes_exact_frozen_feature() -> None:
    close = _utc(FIRST_WARMUP_CLOSE)
    row = synthetic_row(symbol="BTCUSDT", logical_close=close)
    normalized = normalize_provider_row(
        symbol="BTCUSDT",
        logical_close=close,
        raw_row=row,
        observed_at=close + timedelta(minutes=7),
    )
    assert normalized.symbol == "BTCUSDT"
    assert normalized.logical_close_utc == FIRST_WARMUP_CLOSE
    assert normalized.phase == "CONTROL_WARMUP"
    assert normalized.quote_asset_volume == "1001000"
    assert normalized.taker_buy_quote_asset_volume == "510510"
    assert normalized.signed_taker_quote_imbalance == "0.02"
    assert len(normalized.raw_row_sha256) == 64


def test_provider_identity_and_required_field_failures_are_closed() -> None:
    close = _utc(FIRST_WARMUP_CLOSE)
    good = synthetic_row(symbol="BTCUSDT", logical_close=close)

    wrong_open = list(good)
    wrong_open[0] += 1
    with pytest.raises(RecorderBlocked, match="open_time"):
        normalize_provider_row(
            symbol="BTCUSDT",
            logical_close=close,
            raw_row=wrong_open,
            observed_at=close,
        )

    wrong_close = list(good)
    wrong_close[6] -= 1
    with pytest.raises(RecorderBlocked, match="close_time"):
        normalize_provider_row(
            symbol="BTCUSDT",
            logical_close=close,
            raw_row=wrong_close,
            observed_at=close,
        )

    zero_quote = list(good)
    zero_quote[7] = "0"
    with pytest.raises(RecorderBlocked, match="quote_asset_volume"):
        normalize_provider_row(
            symbol="BTCUSDT",
            logical_close=close,
            raw_row=zero_quote,
            observed_at=close,
        )

    excessive_taker = list(good)
    excessive_taker[10] = "2000000"
    with pytest.raises(RecorderBlocked, match="cannot exceed"):
        normalize_provider_row(
            symbol="BTCUSDT",
            logical_close=close,
            raw_row=excessive_taker,
            observed_at=close,
        )

    non_finite = list(good)
    non_finite[4] = "NaN"
    with pytest.raises(RecorderBlocked, match="finite"):
        normalize_provider_row(
            symbol="BTCUSDT",
            logical_close=close,
            raw_row=non_finite,
            observed_at=close,
        )

    with pytest.raises(RecorderBlocked, match="exactly 12"):
        normalize_provider_row(
            symbol="BTCUSDT",
            logical_close=close,
            raw_row=good[:-1],
            observed_at=close,
        )


def test_batch_requires_exact_five_symbol_panel() -> None:
    close = _utc(FIRST_WARMUP_CLOSE)
    rows = synthetic_batch(close)
    normalized = normalize_batch(
        logical_close=close,
        rows=rows,
        observed_at=close + timedelta(minutes=7),
    )
    assert tuple(row.symbol for row in normalized) == PANEL

    incomplete = dict(rows)
    incomplete.pop("XRPUSDT")
    with pytest.raises(RecorderBlocked, match="exactly frozen panel"):
        normalize_batch(
            logical_close=close,
            rows=incomplete,
            observed_at=close + timedelta(minutes=7),
        )


def test_ledger_stages_idempotently_and_conflicts_fail_closed(tmp_path: Path) -> None:
    close = _utc(FIRST_WARMUP_CLOSE)
    observed_at = close + timedelta(minutes=7)
    rows = synthetic_batch(close)
    ledger = EvidenceLedger(tmp_path)

    first = ledger.record_batch(logical_close=close, rows=rows, observed_at=observed_at)
    second = ledger.record_batch(logical_close=close, rows=rows, observed_at=observed_at)
    assert second == first
    assert len(ledger.events()) == 1
    assert first["event_type"] == "OBSERVATION_STAGED"
    assert first["payload"]["durable_scientific_state"] == "OBSERVED_PENDING_ANCHOR"
    assert first["payload"]["backfill"] == "FORBIDDEN"
    assert len(first["payload"]["rows"]) == 5
    assert ledger.ledger_sha256() is not None

    conflicting = synthetic_batch(close)
    conflicting["BTCUSDT"][4] = "999"
    with pytest.raises(RecorderBlocked, match="conflicting second observation"):
        ledger.record_batch(
            logical_close=close,
            rows=conflicting,
            observed_at=observed_at,
        )
    assert len(ledger.events()) == 1


def test_missed_hour_is_recorded_and_cannot_be_backfilled(tmp_path: Path) -> None:
    close = _utc(FIRST_WARMUP_CLOSE)
    ledger = EvidenceLedger(tmp_path)
    with pytest.raises(RecorderBlocked, match="before its deadline"):
        ledger.mark_missed(logical_close=close, detected_at=close + timedelta(minutes=59))

    missed = ledger.mark_missed(logical_close=close, detected_at=close + timedelta(hours=1))
    repeated = ledger.mark_missed(logical_close=close, detected_at=close + timedelta(hours=2))
    assert repeated == missed
    assert missed["event_type"] == "WINDOW_MISSED"
    assert missed["payload"]["backfill"] == "FORBIDDEN"
    assert missed["payload"]["scientific_validity"] == "INVALID_MISSING_PROSPECTIVE_OBSERVATION"

    with pytest.raises(RecorderBlocked, match="recording window missed"):
        ledger.record_batch(
            logical_close=close,
            rows=synthetic_batch(close),
            observed_at=close + timedelta(hours=1, minutes=1),
        )
    assert len(ledger.events()) == 1


def test_row_validity_and_no_authority_are_frozen_before_warmup() -> None:
    assert len(ROW_VALIDITY_RULES) == 14
    assert any("no discretionary magnitude" in rule for rule in ROW_VALIDITY_RULES)
    assert NO_AUTHORITY == {
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

    qualification = json.loads(QUALIFICATION.read_text(encoding="utf-8"))
    assert qualification["state"] == "IMPLEMENTED_UNQUALIFIED"
    assert qualification["candidate_id"] == CANDIDATE_ID
    assert qualification["row_validity_freeze"]["deadline_utc"] == FIRST_WARMUP_CLOSE
    assert qualification["row_validity_freeze"]["discretionary_magnitude_filtering"] == "FORBIDDEN"
    assert qualification["gap_semantics"]["campaign_terminal_on_single_gap"] is False
    assert qualification["phase_authority"]["real_market_data_access_authorized"] is False
    assert qualification["phase_authority"]["scheduler_authorized"] is False
    assert qualification["phase_authority"]["prospective_activation_authorized"] is False
