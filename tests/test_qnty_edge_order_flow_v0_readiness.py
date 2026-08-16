from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from qntylab.qnty_edge_order_flow_v0_readiness import (
    ReadinessError,
    build_coverage_census,
    claim_transition,
    cost_contract,
    execution_identity,
    feature_at,
    funding_cashflow,
    open_to_open_trade,
    position_from_feature,
    prior_24_bar_median_scale,
    require_funding_events,
    signed_taker_quote_notional,
    turnover,
    validate_partition_semantics,
)


def _rows(count: int = 32) -> list[dict[str, str]]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        {
            "timestamp": (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": str(100 + i),
            "quote_volume": "100",
            "taker_buy_quote_volume": "60",
        }
        for i in range(count)
    ]


def test_partition_is_fail_closed_and_sell_is_total_minus_buy() -> None:
    result = validate_partition_semantics(total_quote="100", taker_buy_quote="60", admitted=True)
    assert result["sell_aggressor_quote"] == "40"
    assert signed_taker_quote_notional({"quote_volume": "100", "taker_buy_quote_volume": "60"}, source_partition_proven=True) == Decimal("20")
    with pytest.raises(ReadinessError, match="UNPROVEN"):
        signed_taker_quote_notional({"quote_volume": "100", "taker_buy_quote_volume": "60"}, source_partition_proven=False)


def test_required_fields_are_causal_and_gap_bar_is_not_used() -> None:
    rows = _rows()
    assert prior_24_bar_median_scale(rows, 30) == Decimal("100")
    before = feature_at(rows, 30, source_partition_proven=True)
    rows[29]["quote_volume"] = "999999"
    rows[29]["taker_buy_quote_volume"] = "1"
    rows[30]["quote_volume"] = "888888"
    rows[30]["taker_buy_quote_volume"] = "2"
    assert feature_at(rows, 30, source_partition_proven=True) == before
    rows[28]["taker_buy_quote_volume"] = "90"
    assert feature_at(rows, 30, source_partition_proven=True) != before
    assert position_from_feature(Decimal("0")) == 0
    assert position_from_feature(Decimal("-1")) == -1


def test_open_to_open_is_not_close_to_close() -> None:
    rows = _rows()
    trade = open_to_open_trade(rows, 30, 1)
    assert trade.entry_open == Decimal("130")
    assert trade.exit_open == Decimal("131")
    assert trade.source_bar_end == "2024-01-02T05:00:00Z"
    rows[31]["timestamp"] = "2024-01-02T08:00:00Z"
    with pytest.raises(ReadinessError, match="OPEN_TO_OPEN_GAP"):
        open_to_open_trade(rows, 30, 1)


def test_cost_turnover_and_realized_funding_semantics() -> None:
    assert turnover(0, 1) == 1
    assert turnover(1, 0) == 1
    assert turnover(1, -1) == 2
    assert cost_contract("BASELINE", 0, 1) == {"mode": "BASELINE", "turnover_units": 1, "fee": Decimal("0.001"), "slippage": Decimal("0")}
    assert cost_contract("STRESS", 1, -1)["slippage"] == Decimal("0.002")
    assert funding_cashflow(1, "0.0001", event_time="2024-01-01T08:00:00Z", held_start="2024-01-01T00:00:00Z", held_end="2024-01-01T09:00:00Z") == Decimal("-0.0001")
    assert funding_cashflow(1, "0.0001", event_time="2024-01-01T09:00:00Z", held_start="2024-01-01T00:00:00Z", held_end="2024-01-01T09:00:00Z") == Decimal("0")
    with pytest.raises(ReadinessError, match="MISSING_FUNDING"):
        require_funding_events(None)


def test_census_keeps_all_20_symbols_all_three_blocks_and_40_cells() -> None:
    census = build_coverage_census(__import__("pathlib").Path(__file__).resolve().parents[1])
    assert census["ordered_symbols"] == ["BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT", "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT", "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT", "LDOUSDT", "APTUSDT"]
    assert census["window_count"] == 60
    assert census["scientific_asset_cost_cells"] == 40
    assert census["denominator_preserved"] is True
    assert census["diagnostics_non_eligible_for_survivor"] is True
    assert census["window_counts_by_period"]["DEV_2022"]["BLOCKED_MISSING_PRICE"] == 20
    assert census["window_counts_by_period"]["DEV_2024"]["BLOCKED_MISSING_TAKER_FIELD"] == 20
    assert census["window_counts_by_period"]["DEV_2025"]["BLOCKED_MISSING_PRICE"] == 20


def test_execution_identity_and_duplicate_result_guard() -> None:
    identity = execution_identity(["a" * 64], "b" * 64)
    assert len(identity) == 64
    assert claim_transition("NOT_STARTED", "IN_PROGRESS") == "IN_PROGRESS"
    assert claim_transition("IN_PROGRESS", "TECHNICAL_FAILURE_NO_RESULT") == "TECHNICAL_FAILURE_NO_RESULT"
    with pytest.raises(ReadinessError, match="DUPLICATE"):
        claim_transition("COMPLETED_VALID", "IN_PROGRESS")
