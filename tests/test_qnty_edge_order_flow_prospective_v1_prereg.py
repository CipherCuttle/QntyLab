from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREREG = (
    ROOT
    / "experiments"
    / "research"
    / "qnty_edge_discovery_order_flow_v1"
    / "preregistration.json"
)


def _load() -> dict:
    return json.loads(PREREG.read_text(encoding="utf-8"))


def _stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo == UTC
    return parsed


def test_order_flow_v1_is_new_prospective_only_identity() -> None:
    doc = _load()
    assert doc["candidate_id"] == (
        "CANDIDATE_ORDER_FLOW_SIGNED_TAKER_QUOTE_IMBALANCE_INCREMENTAL_RETURN_V1"
    )
    assert doc["new_candidate_identity"] is True
    assert doc["historical_v0_reopened"] is False
    assert doc["parent_historical_disposition"] == "CLOSED_BLOCKED_GRAVEYARDED_NO_RESCUE"
    assert doc["source_contract"]["historical_archive_materialization_authorized"] is False


def test_order_flow_v1_fixed_panel_and_window_are_frozen() -> None:
    doc = _load()
    assert doc["fixed_symbols"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
    ]
    window = doc["prospective_window"]
    assert window["first_origin_utc"] == "2026-09-16T00:00:00Z"
    assert window["last_origin_utc"] == "2027-01-13T23:00:00Z"
    assert window["scheduled_hours"] == 2880
    assert window["calendar_days"] == 120
    assert window["backfill"] == "FORBIDDEN"
    assert window["replacement_origins"] == "FORBIDDEN"
    assert window["window_extension"] == "FORBIDDEN"

    start = _stamp(window["first_origin_utc"])
    end = _stamp(window["last_origin_utc"])
    assert int((end - start).total_seconds() // 3600) + 1 == 2880


def test_order_flow_v1_warmup_is_prospective_non_evaluated_and_exact() -> None:
    doc = _load()
    warmup = doc["warmup_contract"]
    start = _stamp(warmup["first_warmup_logical_close_utc"])
    end = _stamp(warmup["last_warmup_logical_close_utc"])
    first_origin = _stamp(doc["prospective_window"]["first_origin_utc"])

    assert start == datetime(2026, 9, 15, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 15, 23, tzinfo=UTC)
    assert warmup["warmup_completed_bars"] == 24
    assert int((end - start).total_seconds() // 3600) + 1 == 24
    assert first_origin - end == timedelta(hours=1)
    assert warmup["provider_open_time_range_utc"] == (
        "2026-09-14T23:00:00Z..2026-09-15T22:00:00Z"
    )
    assert warmup["prospective_collection_only"] is True
    assert warmup["backfill"] == "FORBIDDEN"
    assert warmup["feature_or_outcome_evaluation"] == "FORBIDDEN"


def test_order_flow_v1_source_and_feature_semantics_are_exact() -> None:
    doc = _load()
    source = doc["source_contract"]
    assert source["provider"] == "Binance first-party USD-M Futures REST"
    assert source["endpoint"] == "/fapi/v1/klines"
    assert source["interval"] == "1h"
    assert source["required_fields"] == {
        "open_time": 0,
        "open": 1,
        "close": 4,
        "provider_close_time": 6,
        "quote_asset_volume": 7,
        "taker_buy_quote_asset_volume": 10,
    }
    assert "open_time = C - 1h" in source["bar_identity"]
    assert "close_time = C - 1ms" in source["bar_identity"]
    assert source["logical_close_to_provider_query"] == (
        "For an inclusive logical close range [A,B], request provider kline open times "
        "from A-1h through B-1h inclusive."
    )
    assert source["alternative_taker_volume_endpoint_authorized"] is False

    feature = doc["feature_contract"]
    assert feature["formula"] == (
        "(2 * taker_buy_quote_asset_volume_t - quote_asset_volume_t) / quote_asset_volume_t"
    )
    assert feature["zero_quote_volume"] == "ORIGIN_INVALID_FAIL_CLOSED"
    assert feature["out_of_domain"] == "ORIGIN_INVALID_FAIL_CLOSED"
    assert feature["winsorization"] == "NONE"


def test_order_flow_v1_first_origin_has_exact_control_history_contract() -> None:
    doc = _load()
    controls = doc["control_contract"]
    assert "2026-09-15T00:00:00Z through 2026-09-16T00:00:00Z inclusive" in (
        controls["first_origin_history_requirement"]
    )
    outcome = doc["outcome_contract"]
    assert outcome["outcome_candle_identity"] == (
        "For logical origin C, outcome candle provider open_time = C and logical close "
        "boundary = C+1h."
    )


def test_order_flow_v1_primary_model_and_gate_are_frozen() -> None:
    doc = _load()
    model = doc["primary_model"]
    assert model["primary_parameter"] == "beta_signed_taker_quote_imbalance"
    assert model["directional_hypothesis"] == "beta_signed_taker_quote_imbalance > 0"
    assert model["primary_alpha_two_sided"] == 0.01
    assert model["hac_lag_hours"] == 24
    conditions = doc["terminal_support_gate"]["conditions"]
    assert "at least 4 of 5 symbol-specific diagnostic slopes are > 0" in conditions
    assert "each symbol has at least 90% of its 2880 scheduled origins valid" in conditions


def test_order_flow_v1_preregistration_grants_no_execution_authority() -> None:
    doc = _load()
    firewall = doc["firewall"]
    assert firewall["warmup_values_may_not_be_used_for_model_changes"] is True
    assert firewall["interim_scientific_evaluation"] is False
    assert firewall["interim_p_values"] is False
    assert firewall["interim_edge_verdict"] is False
    assert firewall["economic_strategy_translation_authorized"] is False

    authority = doc["phase_authority"]
    assert authority == {
        "market_data_access_authorized": False,
        "collector_implementation_authorized": False,
        "prospective_activation_authorized": False,
        "scientific_execution_authorized": False,
        "terminal_evaluation_authorized": False,
        "router_authorized": False,
        "qnty_authorized": False,
        "qntyspot_authorized": False,
        "trading_authorized": False,
        "capital_authority": "NONE",
    }
