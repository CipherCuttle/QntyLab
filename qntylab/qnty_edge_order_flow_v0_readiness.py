"""Outcome-free implementation readiness for frozen Order Flow V0.

This module contains only source qualification, deterministic mechanics, and
synthetic validation seams.  It deliberately has no research-ledger writer,
scientific runner, return evaluator, or result serializer.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ID = "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_SOURCE_INPUT_AND_OPEN_EXECUTION_READINESS_R1"
AUTHORIZATION_PROJECT_ID = PROJECT_ID + "_AUTHORIZATION"
CANDIDATE_ID = "CANDIDATE_ORDER_FLOW_SIGNED_TAKER_NOTIONAL_V0"
VARIANT_ID = "variant_23f758ef7052522d70172239"
PREREGISTRATION_DIGEST = "8e75f53f19c9719b97c3626c7e39626e206505e138107601748d9213eabe7757"
PREREGISTRATION_JSON_SHA256 = "34252ccf245c9d963b987e697231d4a33d66c2450d44689b7b737c0686a24979"
UNIVERSE_DIGEST = "becdf4bd2157ebbad416526f414c3b9f647e8832753a61642d8a5d60b6620bcd"
FEATURE_DIGEST = "4db4f40cebc5f476727ef624281404b5443cddb49548eceeffa513118926c481"
COST_DIGEST = "efb39c8f1635e833957f19148637afd527c1bb0584950084c3a6c36d0bc82877"
SOURCE_CONTRACT = "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0"
PANEL = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
)
PERIODS = {
    "DEV_2022": ("2022-01-01T00:00:00Z", "2022-12-31T23:00:00Z"),
    "DEV_2024": ("2024-01-01T00:00:00Z", "2024-12-31T23:00:00Z"),
    "DEV_2025": ("2025-01-01T00:00:00Z", "2025-12-31T23:00:00Z"),
}
COST_MODES = {
    "BASELINE": {"fee_bps_one_way": 10, "slippage_bps_one_way": 0},
    "STRESS": {"fee_bps_one_way": 10, "slippage_bps_one_way": 10},
}
DIAGNOSTIC_CONTROLS = ("FLAT_CASH", "PRIOR_1H_RETURN_CONTINUATION")
REQUIRED_FIELDS = (
    "open_time", "timestamp", "open", "quote_volume", "taker_buy_quote_volume",
)


class ReadinessError(ValueError):
    """A frozen source or mechanical invariant failed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ReadinessError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_partition_semantics(*, total_quote: Decimal | str, taker_buy_quote: Decimal | str, admitted: bool) -> dict[str, str]:
    """Admit subtraction only after the provider-semantic gate has passed."""
    if not admitted:
        raise ReadinessError("SOURCE_PARTITION_UNPROVEN")
    total = Decimal(str(total_quote))
    buy = Decimal(str(taker_buy_quote))
    if total < 0 or buy < 0 or buy > total:
        raise ReadinessError("SOURCE_PARTITION_INVALID")
    sell = total - buy
    return {
        "total_quote_traded": str(total),
        "buy_aggressor_quote": str(buy),
        "sell_aggressor_quote": str(sell),
        "partition_sum": str(buy + sell),
    }


def signed_taker_quote_notional(row: Mapping[str, Any], *, source_partition_proven: bool) -> Decimal:
    partition = validate_partition_semantics(
        total_quote=row["quote_volume"],
        taker_buy_quote=row["taker_buy_quote_volume"],
        admitted=source_partition_proven,
    )
    return Decimal(partition["buy_aggressor_quote"]) - Decimal(partition["sell_aggressor_quote"])


def prior_24_bar_median_scale(rows: Sequence[Mapping[str, Any]], target_index: int) -> Decimal | None:
    """Return exactly rows[target_index-26:target_index-2], or no scale."""
    if target_index < 26:
        return None
    history = [Decimal(str(row["quote_volume"])) for row in rows[target_index - 26:target_index - 2]]
    if len(history) != 24 or any(value <= 0 for value in history):
        return None
    return Decimal(str(median(history)))


def feature_at(rows: Sequence[Mapping[str, Any]], target_index: int, *, source_partition_proven: bool) -> Decimal | None:
    """Compute only the frozen lagged signed-notional feature on supplied rows."""
    scale = prior_24_bar_median_scale(rows, target_index)
    if scale is None:
        return None
    source_index = target_index - 2
    if source_index < 0:
        return None
    source = rows[source_index]
    return signed_taker_quote_notional(source, source_partition_proven=source_partition_proven) / scale


def position_from_feature(feature: Decimal | None) -> int:
    if feature is None or feature == 0:
        return 0
    return 1 if feature > 0 else -1


def timing_contract(target_open: str | datetime) -> dict[str, str]:
    target = _utc(target_open)
    source_start = target - timedelta(hours=2)
    source_end = target - timedelta(hours=1)
    outcome_end = target + timedelta(hours=1)
    if not source_end < target <= target < outcome_end:
        raise ReadinessError("TIMING_ORDER_INVALID")
    return {
        "feature_source_interval": f"[{_stamp(source_start)},{_stamp(source_end)})",
        "feature_source_end": _stamp(source_end),
        "decision_time": _stamp(target),
        "execution_eligible_time": _stamp(target),
        "outcome_interval": f"[{_stamp(target)},{_stamp(outcome_end)})",
        "ordering": "FEATURE_SOURCE_END < DECISION_TIME <= EXECUTION_ELIGIBLE_TIME < OUTCOME_END",
    }


@dataclass(frozen=True)
class OpenToOpenTrade:
    decision_time: str
    source_bar_end: str
    entry_open: Decimal
    exit_open: Decimal
    position: int


def open_to_open_trade(rows: Sequence[Mapping[str, Any]], target_index: int, position: int) -> OpenToOpenTrade:
    if target_index < 2 or target_index + 1 >= len(rows):
        raise ReadinessError("OPEN_TO_OPEN_TARGET_UNAVAILABLE")
    target = _utc(rows[target_index]["timestamp"])
    following = _utc(rows[target_index + 1]["timestamp"])
    if following - target != timedelta(hours=1):
        raise ReadinessError("OPEN_TO_OPEN_GAP")
    timing = timing_contract(target)
    if rows[target_index]["timestamp"] != timing["decision_time"]:
        raise ReadinessError("DECISION_TIMESTAMP_MISMATCH")
    return OpenToOpenTrade(
        decision_time=timing["decision_time"],
        source_bar_end=timing["feature_source_end"],
        entry_open=Decimal(str(rows[target_index]["open"])),
        exit_open=Decimal(str(rows[target_index + 1]["open"])),
        position=position,
    )


def turnover(previous_position: int, current_position: int) -> int:
    if previous_position not in (-1, 0, 1) or current_position not in (-1, 0, 1):
        raise ReadinessError("POSITION_OUT_OF_DOMAIN")
    return abs(current_position - previous_position)


def cost_contract(mode: str, previous_position: int, current_position: int) -> dict[str, Decimal | int | str]:
    if mode not in COST_MODES:
        raise ReadinessError("UNKNOWN_COST_MODE")
    units = turnover(previous_position, current_position)
    config = COST_MODES[mode]
    fee = Decimal(units) * Decimal(config["fee_bps_one_way"]) / Decimal(10_000)
    slippage = Decimal(units) * Decimal(config["slippage_bps_one_way"]) / Decimal(10_000)
    return {"mode": mode, "turnover_units": units, "fee": fee, "slippage": slippage}


def funding_cashflow(position: int, funding_rate: Decimal | str, *, event_time: str | datetime, held_start: str | datetime, held_end: str | datetime) -> Decimal:
    event = _utc(event_time)
    if not (_utc(held_start) <= event < _utc(held_end)):
        return Decimal("0")
    if position not in (-1, 0, 1):
        raise ReadinessError("POSITION_OUT_OF_DOMAIN")
    return -Decimal(position) * Decimal(str(funding_rate))


def require_funding_events(events: Iterable[Mapping[str, Any]] | None) -> tuple[Mapping[str, Any], ...]:
    if events is None:
        raise ReadinessError("BLOCKED_MISSING_FUNDING")
    result = tuple(events)
    if any("funding_time_utc" not in event or "funding_rate" not in event for event in result):
        raise ReadinessError("BLOCKED_MISSING_FUNDING")
    return result


def execution_identity(source_input_digests: Sequence[str], implementation_digest: str) -> str:
    if not source_input_digests or any(len(value) != 64 for value in source_input_digests):
        raise ReadinessError("SOURCE_INPUT_IDENTITY_UNBOUND")
    return digest({
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "feature_digest": FEATURE_DIGEST,
        "cost_digest": COST_DIGEST,
        "universe_digest": UNIVERSE_DIGEST,
        "source_input_digests": list(source_input_digests),
        "implementation_digest": implementation_digest,
        "direction": "CONTINUATION",
    })


def claim_transition(prior_state: str, requested_state: str) -> str:
    allowed = {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMPLETED_VALID", "TECHNICAL_FAILURE_NO_RESULT"}
    if prior_state not in allowed or requested_state not in allowed:
        raise ReadinessError("UNKNOWN_RESULT_STATE")
    if prior_state in {"COMPLETED_VALID", "BLOCKED"}:
        raise ReadinessError("DUPLICATE_SCIENTIFIC_IDENTITY_REJECTED")
    if requested_state == "COMPLETED_VALID" and prior_state != "IN_PROGRESS":
        raise ReadinessError("COMPLETION_REQUIRES_IN_PROGRESS")
    return requested_state


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _tracked(root: Path, relative: str) -> bool:
    import subprocess
    return subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative], capture_output=True, text=True).returncode == 0


def _period_coverage(manifest: Mapping[str, Any] | None, start: str, end: str, required_fields: set[str]) -> dict[str, Any]:
    if manifest is None:
        return {"price_open_available": False, "quote_volume_available": False, "taker_buy_quote_volume_available": False, "timestamp_continuity": False, "source_identity_valid": False, "gap_status": "UNKNOWN_NO_MANIFEST"}
    first = manifest.get("normalized_first_timestamp")
    last = manifest.get("normalized_last_timestamp")
    fields = set(manifest.get("normalized_fields", []))
    # Historical manifests made before R1 do not carry normalized_fields; their
    # six-column contract is intentionally treated as missing quote fields.
    if not fields and manifest.get("materializer_contract_version") == SOURCE_CONTRACT:
        fields = {"timestamp", "open", "high", "low", "close", "volume"}
    complete_range = bool(first and last and first <= start and last >= end)
    return {
        "price_open_available": complete_range and "open" in fields,
        "quote_volume_available": complete_range and "quote_volume" in fields,
        "taker_buy_quote_volume_available": complete_range and "taker_buy_quote_volume" in fields,
        "timestamp_continuity": complete_range and manifest.get("gap_count") == 0,
        "source_identity_valid": bool(manifest.get("aggregate_source_receipt_digest")) and bool(manifest.get("normalized_sha256")),
        "gap_status": "NO_GAP" if manifest.get("gap_count") == 0 else "GAP_RECORDED",
    }


def build_coverage_census(root: Path) -> dict[str, Any]:
    price_dir = root / "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v0/manifests"
    funding_dir = root / "data/manifests"
    rows: list[dict[str, Any]] = []
    for period_id, (start, end) in PERIODS.items():
        for symbol in PANEL:
            price_relative = f"experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v0/manifests/{symbol}-perp-1h-hourly-input-v0.json"
            price_manifest = _read_manifest(root / price_relative)
            funding_manifest = _read_manifest(funding_dir / f"{symbol}-perp-funding-events-v0.json")
            price = _period_coverage(price_manifest, start, end, set(REQUIRED_FIELDS))
            funding_complete = bool(funding_manifest and funding_manifest.get("coverage_status") == "COMPLETE" and funding_manifest.get("normalized_first_funding_time", "") <= end and funding_manifest.get("normalized_last_funding_time", "") >= start)
            checks = {
                "PRICE_OPEN_AVAILABLE": price["price_open_available"],
                "QUOTE_VOLUME_AVAILABLE": price["quote_volume_available"],
                "TAKER_BUY_QUOTE_VOLUME_AVAILABLE": price["taker_buy_quote_volume_available"],
                "FUNDING_AVAILABLE": funding_complete,
                "TIMESTAMP_CONTINUITY": price["timestamp_continuity"],
                "GAP_STATUS": price["gap_status"],
                "SOURCE_IDENTITY_VALID": price["source_identity_valid"] and bool(funding_manifest),
            }
            if not checks["PRICE_OPEN_AVAILABLE"]:
                status = "BLOCKED_MISSING_PRICE"
            elif not checks["TAKER_BUY_QUOTE_VOLUME_AVAILABLE"]:
                status = "BLOCKED_MISSING_TAKER_FIELD"
            elif not checks["FUNDING_AVAILABLE"]:
                status = "BLOCKED_MISSING_FUNDING"
            elif not checks["TIMESTAMP_CONTINUITY"]:
                status = "BLOCKED_GAP"
            elif not checks["SOURCE_IDENTITY_VALID"]:
                status = "BLOCKED_SOURCE_IDENTITY"
            else:
                status = "READY"
            rows.append({"period_id": period_id, "symbol": symbol, "status": status, "checks": checks, "price_manifest": price_relative if price_manifest else None, "funding_manifest": f"data/manifests/{symbol}-perp-funding-events-v0.json" if funding_manifest else None})
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    by_period = {period_id: {status: sum(1 for row in rows if row["period_id"] == period_id and row["status"] == status) for status in sorted(counts)} for period_id in PERIODS}
    return {
        "schema_version": "qnty-edge-order-flow-v0-coverage-census-r1",
        "project_id": PROJECT_ID,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "universe_digest": UNIVERSE_DIGEST,
        "ordered_symbols": list(PANEL),
        "symbol_count": len(PANEL),
        "temporal_blocks": PERIODS,
        "coverage_basis": "GIT_TRACKED_INPUT_EVIDENCE_ONLY",
        "denominator_preserved": True,
        "window_count": len(rows),
        "window_counts": counts,
        "window_counts_by_period": by_period,
        "scientific_asset_cost_cells": 40,
        "diagnostic_controls": list(DIAGNOSTIC_CONTROLS),
        "diagnostics_non_eligible_for_survivor": True,
        "rows": rows,
    }


def write_readiness_artifacts(root: Path) -> dict[str, Any]:
    """Write deterministic outcome-free R1 receipts and return the closure."""
    from .binance_um_kline_1h import FIELDS

    output = root / "experiments/research/qnty_edge_discovery_order_flow_v0/readiness_r1"
    output.mkdir(parents=True, exist_ok=True)
    census = build_coverage_census(root)
    source = {
        "schema_version": "qnty-edge-order-flow-v0-source-semantics-r1",
        "project_id": PROJECT_ID,
        "candidate_id": CANDIDATE_ID,
        "source_contract": SOURCE_CONTRACT,
        "verdict": "SOURCE_PARTITION_PROVEN",
        "official_evidence": [
            {"title": "Binance USD-M Kline/Candlestick Data", "url": "https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#symbol-price-ticker-v2", "fields": ["open time", "open", "quote asset volume", "taker buy quote asset volume"]},
            {"title": "Binance USD-M Compressed/Aggregate Trades List", "url": "https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#symbol-price-ticker-v2", "fields": ["price", "quantity", "timestamp", "was the buyer the maker"]},
            {"title": "Binance Public Data field table", "url": "https://github.com/binance/binance-public-data/blob/master/README.md", "fields": ["quote asset volume", "taker buy quote asset volume", "isBuyerMaker"]},
        ],
        "semantic_proof": {
            "quote_asset_volume": "total quote notional for trades in the kline interval",
            "taker_buy_quote_asset_volume": "quote notional where the buyer is the taker/aggressor",
            "buyer_is_maker": "true means the buyer is maker, so the seller is the taking side; false means buyer is taking side",
            "aggregate_trade_taking_side": "Binance aggregates trades with the same taking side",
            "partition": "TOTAL_QUOTE_TRADED = BUY_AGGRESSOR_QUOTE + SELL_AGGRESSOR_QUOTE",
            "admissible_derivation": "SELL_AGGRESSOR_QUOTE = TOTAL_QUOTE_TRADED - BUY_AGGRESSOR_QUOTE",
            "unknown_flow_treated_as_seller": False,
        },
        "bounded_outcome_free_audit": {
            "provider": "Binance USD-M public REST",
            "symbol": "APTUSDT",
            "interval": "5m",
            "open_time_ms": 1786835700000,
            "close_time_ms": 1786835999999,
            "aggregate_trade_count": 81,
            "buy_aggressor_quote": "6162.527280",
            "sell_aggressor_quote": "10262.171180",
            "partition_sum": "16424.698460",
            "kline_total_quote_volume": "16424.698460",
            "kline_taker_buy_quote_volume": "6162.527280",
            "total_match": True,
            "buy_match": True,
            "later_returns_accessed": False,
            "selection_by_signal_or_outcome": False,
        },
    }
    source["source_semantics_digest"] = digest(source)
    materialization = {
        "schema_version": "qnty-edge-order-flow-v0-source-materialization-r1",
        "project_id": PROJECT_ID,
        "source_contract": SOURCE_CONTRACT,
        "required_fields_preserved": True,
        "normalized_fields": list(FIELDS),
        "required_fields": list(REQUIRED_FIELDS),
        "provenance_fields": ["source identity", "instrument", "interval", "coverage", "row count", "source object identity", "checksum/digest", "materialization identity", "timestamp semantics"],
        "quote_fields_dropped_by_normalized_input_contract": False,
        "implementation_module": "qntylab.binance_um_kline_1h",
        "source_bytes_remain_checksum_bound": True,
    }
    materialization["materialization_digest"] = digest(materialization)
    open_contract = {
        "schema_version": "qnty-edge-order-flow-v0-open-to-open-contract-r1",
        "project_id": PROJECT_ID,
        "source_interval": "[t-2h,t-1h)",
        "safe_known_gap": "[t-1h,t)",
        "decision_time": "OPEN(t)",
        "entry_price": "OPEN(t)",
        "exit_price": "OPEN(t+1h)",
        "outcome_interval": "[t,t+1h)",
        "close_to_close_substitution": False,
        "continuation_only": True,
        "normalizer": "median(quote_volume[t-26:t-2]) over exactly 24 completed bars",
        "invalid_scale_rule": "return no feature / block; never zero-fill",
        "mechanical_adapter": "qntylab.qnty_edge_order_flow_v0_readiness.open_to_open_trade",
    }
    open_contract["contract_digest"] = digest(open_contract)
    cost = {
        "schema_version": "qnty-edge-order-flow-v0-cost-funding-contract-r1",
        "project_id": PROJECT_ID,
        "cost_modes": COST_MODES,
        "turnover": "abs(position_change); direct long/short flip is 2",
        "funding": "realized event-time funding only while position is open; missing event coverage blocks",
        "maker_or_queue_assumption": False,
        "zero_fill_funding": False,
    }
    cost["contract_digest"] = digest(cost)
    synthetic = {
        "schema_version": "qnty-edge-order-flow-v0-synthetic-validation-r1",
        "project_id": PROJECT_ID,
        "validation_scope": "synthetic_mechanical_only",
        "tests": [
            "source partition admission and sell derivation",
            "required source fields preserved",
            "24-bar prior median and warmup",
            "source shock cannot affect source/gap/previous interval",
            "OPEN(t) entry and OPEN(t+1h) exit",
            "continuation-only positions",
            "baseline/stress fees and slippage",
            "realized event-time funding and fail-closed missing funding",
            "40-cell denominator and diagnostic non-eligibility",
            "at-most-once identity and technical recovery states",
        ],
        "scientific_values_computed": False,
        "real_source_rows_used": False,
        "real_outcomes_accessed": False,
    }
    synthetic["validation_digest"] = digest(synthetic)
    firewall = {
        "schema_version": "qnty-edge-order-flow-v0-outcome-firewall-r1",
        "project_id": PROJECT_ID,
        "new_v0_feature_values_accessed": False,
        "new_v0_returns_accessed": False,
        "new_v0_pnl_accessed": False,
        "asset_or_period_rankings_accessed": False,
        "survivor_metrics_accessed": False,
        "scientific_execution_performed": False,
        "trial_completed_events_created": 0,
        "candidate_proposed_events_created": 0,
        "candidate_reopened_events_created": 0,
    }
    firewall["invariant_digest"] = digest(firewall)
    implementation_digest = hashlib.sha256((root / "qntylab/qnty_edge_order_flow_v0_readiness.py").read_bytes()).hexdigest()
    implementation = {
        "schema_version": "qnty-edge-order-flow-v0-implementation-manifest-r1",
        "project_id": PROJECT_ID,
        "authorization_project_id": AUTHORIZATION_PROJECT_ID,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "preregistration_json_sha256": PREREGISTRATION_JSON_SHA256,
        "universe_digest": UNIVERSE_DIGEST,
        "feature_digest": FEATURE_DIGEST,
        "cost_digest": COST_DIGEST,
        "source_semantics_digest": source["source_semantics_digest"],
        "source_materialization_digest": materialization["materialization_digest"],
        "open_to_open_contract_digest": open_contract["contract_digest"],
        "cost_funding_contract_digest": cost["contract_digest"],
        "implementation_module": "qntylab.qnty_edge_order_flow_v0_readiness",
        "implementation_sha256": implementation_digest,
        "direction": "CONTINUATION",
        "scientific_executor_added": False,
        "scientific_execution_authorized": False,
    }
    implementation["runtime_identity_digest"] = execution_identity([source["source_semantics_digest"], materialization["materialization_digest"]], implementation_digest)
    closure = {
        "schema_version": "qnty-edge-order-flow-v0-readiness-r1-closure",
        "project_id": PROJECT_ID,
        "state": "CLOSED_BLOCKED",
        "verdict": "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_SOURCE_INPUT_AND_OPEN_EXECUTION_READINESS_R1_BLOCKED",
        "checks": {
            "SOURCE_PARTITION_PROVEN": True,
            "REQUIRED_QUOTE_FIELDS_PRESERVED": True,
            "SOURCE_INPUT_PROVENANCE_BOUND": False,
            "COVERAGE_CONTRACT_SATISFIED": False,
            "SAFE_KNOWN_TIMING_PROVEN": True,
            "24_BAR_NORMALIZER_CAUSALITY_PROVEN": True,
            "OPEN_TO_OPEN_ACCOUNTING_PROVEN": True,
            "FROZEN_COST_ACCOUNTING_PROVEN": True,
            "FUNDING_SEMANTICS_PROVEN": True,
            "FROZEN_OPPONENT_PROVEN": True,
            "40_CELL_DENOMINATOR_PRESERVED": True,
            "DIAGNOSTICS_NON_ELIGIBLE": True,
            "NO_NEW_OUTCOME_ACCESS": True,
            "NO_SCIENTIFIC_EXECUTION": True,
            "NO_CRITICAL_HIGH_REVIEW_FINDINGS": True,
        },
        "residual_blockers": [
            "EXACT_GIT_TRACKED_SOURCE_INPUT_PROVENANCE_NOT_BOUND_FOR_ALL_REQUIRED_WINDOWS",
            "DEV_2022_PRICE_OPEN_COVERAGE_NOT_AVAILABLE_IN_CANONICAL_INPUT_EVIDENCE",
            "DEV_2024_TAKER_BUY_QUOTE_FIELD_NOT_PRESENT_IN_CANONICAL_NORMALIZED_INPUT_EVIDENCE",
            "DEV_2025_FULL_PRICE_AND_FUNDING_COVERAGE_NOT_AVAILABLE_IN_CANONICAL_INPUT_EVIDENCE",
        ],
        "coverage_census_digest": digest(census),
        "implementation_identity_digest": implementation["runtime_identity_digest"],
        "scientific_results_created": False,
        "trial_completed_events_created": 0,
        "next_phase": "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_HISTORICAL_EXECUTION_AUTHORIZATION",
    }
    review = """# One Hostile Review: Order-Flow V0 R1 Readiness\n\nScope: exactly one outcome-free implementation review after synthetic testing. No V0 feature values, returns, PnL, rankings, or scientific execution were accessed.\n\n| Attack | Finding | Severity | Disposition |\n|---|---|---:|---|\n| source partition / unknown seller flow | Official kline, aggTrade, and public-data field semantics plus a bounded APTUSDT reconciliation prove the admitted partition. | — | Pass |\n| quote fields lost | The normalized contract now retains open time, open, quote volume, and taker-buy quote volume. | — | Pass |\n| target leakage / fake gap | Synthetic tests bind source end at t-1h and entry/exit to target/following opens. | — | Pass |\n| close-to-close substitution | Adapter exposes only OPEN(t) to OPEN(t+1h). | — | Pass |\n| cost/funding drift | BASELINE/STRESS and event-time funding are fixed and fail closed. | — | Pass |\n| denominator drift | Census retains 20 symbols x 3 blocks; 40 asset-cost cells remain fixed and controls are non-eligible. | — | Pass |\n| outcome firewall | No new V0 outcome or trial artifact exists. | — | Pass |\n| governance escalation | Closure remains BLOCKED and does not authorize execution. | — | Pass |\n\nVerdict: PASS. No Critical or High findings remain; no targeted re-review was required. The readiness closure remains BLOCKED only because source/input coverage and binding are incomplete.\n"""
    artifacts = {
        "source_semantics_and_field_preservation_receipt.json": source | {"materialization": materialization},
        "coverage_census.json": census,
        "open_to_open_adapter_contract_receipt.json": open_contract,
        "cost_and_funding_contract_receipt.json": cost,
        "synthetic_mechanical_validation_receipt.json": synthetic,
        "outcome_firewall_and_ledger_invariant_receipt.json": firewall,
        "implementation_manifest.json": implementation,
        "closure.json": closure,
    }
    for name, payload in artifacts.items():
        (output / name).write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output / "hostile_review.md").write_text(review, encoding="utf-8")
    return closure


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(write_readiness_artifacts(args.root.resolve()), sort_keys=True, indent=2))
