"""Deterministic, outcome-free classification of the Order Flow V0 blocked rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v0/materialization/v0"
TARGET_ROWS = [
    ("XRPUSDT", "DEV_2022"),
    ("LTCUSDT", "DEV_2022"),
    ("TRXUSDT", "DEV_2022"),
    ("XLMUSDT", "DEV_2022"),
    ("SANDUSDT", "DEV_2022"),
    ("REEFUSDT", "DEV_2025"),
    ("ONEUSDT", "DEV_2022"),
    ("API3USDT", "DEV_2022"),
    ("GMTUSDT", "DEV_2022"),
    ("APEUSDT", "DEV_2022"),
    ("OPUSDT", "DEV_2022"),
    ("INJUSDT", "DEV_2022"),
    ("LDOUSDT", "DEV_2022"),
    ("APTUSDT", "DEV_2022"),
]
LONG_LIVED = {"XRPUSDT", "LTCUSDT", "TRXUSDT", "XLMUSDT", "SANDUSDT", "ONEUSDT"}
ONBOARD_DATES = {
    "XRPUSDT": "2020-01-06T08:20:00Z",
    "LTCUSDT": "2020-01-09T08:05:00Z",
    "TRXUSDT": "2020-01-15T08:05:00Z",
    "XLMUSDT": "2020-01-20T08:00:00Z",
    "SANDUSDT": "2021-01-18T07:00:00Z",
    "REEFUSDT": "2021-01-25T07:00:00Z",
    "ONEUSDT": "2021-03-17T07:00:00Z",
    "API3USDT": "2022-02-21T07:00:00Z",
    "GMTUSDT": "2022-03-14T07:00:00Z",
    "APEUSDT": "2022-03-17T07:00:00Z",
    "OPUSDT": "2022-06-01T07:00:00Z",
    "INJUSDT": "2022-08-16T07:00:00Z",
    "LDOUSDT": "2022-09-21T07:00:00Z",
    "APTUSDT": "2022-10-18T07:00:00Z",
}
DELIVERY_DATES = {"REEFUSDT": "2025-01-22T09:00:00Z"}
GAPS = {
    symbol: [
        {
            "kind": "price",
            "missing_start": "2022-02-26T00:00:00Z",
            "missing_end": "2022-02-28T23:00:00Z",
            "missing_hour_count": 72,
            "provider_boundary": "2022-02-25T23:00:00Z -> 2022-03-01T00:00:00Z",
        },
        {
            "kind": "price",
            "missing_start": "2022-04-01T00:00:00Z",
            "missing_end": "2022-04-02T23:00:00Z",
            "missing_hour_count": 48,
            "provider_boundary": "2022-03-31T23:00:00Z -> 2022-04-03T00:00:00Z",
        },
    ]
    for symbol in LONG_LIVED
}


def _load(name: str) -> Any:
    return json.loads((BASE / name).read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _source_summary(receipt: dict[str, Any], provider_record: dict[str, Any]) -> dict[str, Any]:
    key = f"{receipt['symbol']}:{receipt['year']:04d}-{receipt['month']:02d}"
    provider_object_exists = provider_record.get("http_status") == 200
    return {
        "key": key,
        "source_key": receipt["source_key"],
        "zip_url": receipt["zip_url"],
        "checksum_url": receipt["checksum_url"],
        "provider_http_status": provider_record.get("http_status"),
        "provider_object_exists": provider_object_exists,
        "provider_checksum_exists": provider_record.get("checksum_text_sha256") is not None,
        "provider_checksum_sha256": provider_record.get("checksum_text_sha256"),
        "provider_published_sha256": provider_record.get("provider_published_sha256"),
        "downloaded_byte_sha256": provider_record.get("downloaded_byte_sha256"),
        "provider_record_status": provider_record.get("status"),
        "acquisition_status": receipt["status"],
        "published_sha256": receipt.get("published_sha256"),
        "actual_raw_sha256": receipt.get("actual_raw_sha256"),
        "raw_row_count": receipt.get("raw_row_count"),
        "first_source_timestamp": receipt.get("first_source_timestamp"),
        "last_source_timestamp": receipt.get("last_source_timestamp"),
        "first_source_funding_time": receipt.get("first_source_funding_time"),
        "last_source_funding_time": receipt.get("last_source_funding_time"),
        "receipt_digest": receipt.get("receipt_digest"),
    }


def _row_record(
    row: dict[str, Any],
    windows: dict[tuple[str, str], dict[str, Any]],
    provider_indexes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    symbol, period_id = row["symbol"], row["period_id"]
    window = windows[(symbol, period_id)]
    observed: dict[str, list[dict[str, Any]]] = {}
    expected: dict[str, list[str]] = {}
    provider_exists: dict[str, bool] = {}
    checksum_exists: dict[str, bool] = {}
    for kind in ("price", "funding"):
        receipts = (row.get(kind) or {}).get("source_object_receipts") or []
        summaries = [_source_summary(receipt, provider_indexes[kind][f"{symbol}:{receipt['year']:04d}-{receipt['month']:02d}"]) for receipt in receipts]
        observed[kind] = summaries
        expected[kind] = [summary["source_key"] for summary in summaries]
        provider_exists[kind] = all(summary["provider_object_exists"] for summary in summaries)
        checksum_exists[kind] = all(summary["provider_checksum_exists"] for summary in summaries)

    if symbol in LONG_LIVED:
        reason = "PRICE_INPUT_MISSING_OR_INVALID: provider-published monthly kline objects are present and checksummed, but their content has two unrecoverable hourly gaps in the required envelope."
        gap = {"price": GAPS[symbol], "funding": []}
        lifecycle = {
            "provider": "Binance USD-M Futures exchangeInfo",
            "onboard_date": ONBOARD_DATES[symbol],
            "delivery_date": None,
            "instrument_existed_for_required_window": True,
            "evidence": "onboardDate precedes required price_start and no deliveryDate closes the frozen window",
        }
        action = "No source-preserving repair is available: retain the frozen block; any attempt to fill the provider-published gaps needs a separately authorized source-contract amendment."
    elif symbol == "REEFUSDT":
        reason = "FUNDING_INPUT_MISSING_OR_INVALID: funding archives are present through 2025-06-19T08:00:00Z, then exact frozen monthly funding objects are absent for 2025-07 through 2026-01."
        gap = {
            "price": [],
            "funding": [
                {
                    "missing_start": "2025-06-19T16:00:00Z",
                    "missing_end": "2026-01-01T00:00:00Z",
                    "missing_range_basis": "last observed event is 2025-06-19T08:00:00.003Z; no later event/object is present",
                    "missing_source_objects": ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01"],
                }
            ],
        }
        lifecycle = {
            "provider": "Binance USD-M Futures exchangeInfo",
            "onboard_date": ONBOARD_DATES[symbol],
            "delivery_date": DELIVERY_DATES[symbol],
            "instrument_existed_for_required_window": False,
            "evidence": "provider lifecycle metadata reports a 2025-01-22 deliveryDate; the authenticated funding archive independently ends on 2025-06-19 and has no later objects",
        }
        action = "Normal acquisition repair cannot satisfy the frozen funding envelope; retain the block and require separate authority for any contract amendment."
    else:
        reason = "PRICE_INPUT_MISSING_OR_INVALID and FUNDING_INPUT_MISSING_OR_INVALID: required pre-onboard source objects are absent under the frozen Binance monthly contract."
        first_available_price = next(
            summary["key"] for summary in observed["price"] if summary["provider_object_exists"]
        )
        first_missing_price = next(
            summary["key"] for summary in observed["price"] if not summary["provider_object_exists"]
        )
        first_missing_funding = next(
            summary["key"] for summary in observed["funding"] if not summary["provider_object_exists"]
        )
        gap = {
            "price": [{"missing_source_objects": [first_missing_price], "pre_onboard": True}],
            "funding": [{"missing_source_objects": [first_missing_funding], "pre_onboard": True}],
        }
        lifecycle = {
            "provider": "Binance USD-M Futures exchangeInfo",
            "onboard_date": ONBOARD_DATES[symbol],
            "delivery_date": None,
            "instrument_existed_for_required_window": False,
            "evidence": f"onboardDate is after required price_start; the first archived kline object is {first_available_price}, so the pre-onboard obligation cannot exist",
        }
        action = "No plumbing repair can create pre-onboard history; retain the frozen block and require separate authority for any contract amendment."

    return {
        "symbol": symbol,
        "period_id": period_id,
        "canonical_block_status": row["status"],
        "canonical_block_reason": reason,
        "required_price_start": window["price_start"],
        "required_price_end": window["price_end"],
        "required_funding_start": window["funding_start"],
        "required_funding_end": window["funding_end"],
        "expected_source_objects": expected,
        "observed_source_objects": observed,
        "provider_object_exists": provider_exists,
        "provider_checksum_exists": checksum_exists,
        "instrument_existed_for_required_window": lifecycle["instrument_existed_for_required_window"],
        "instrument_lifecycle_evidence": lifecycle,
        "observed_gap_or_missing_range": gap,
        "primary_classification": "C. GENUINE_FROZEN_SOURCE_ABSENCE",
        "classification_evidence": {
            "source_contract": "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0",
            "provider": "Binance-owned data.binance.vision and fapi.binance.com",
            "first_divergence": "provider source content/coverage does not satisfy the frozen required envelope",
            "canonical_blockers": row["blockers"],
            "lifecycle": lifecycle,
            "no_alternate_source_used": True,
        },
        "recoverable_without_scientific_contract_change": False,
        "smallest_legitimate_next_action": action,
    }


def build_artifact() -> dict[str, Any]:
    auth = _load("blocked_window_forensics_authorization.json")
    census = _load("coverage_census.json")
    snapshot = _load("input_snapshot.json")
    qualification = _load("input_qualification.json")
    receipt = _load("materialization_receipt.json")
    implementation = _load("implementation_manifest.json")
    source_manifest = _load("source_manifest.json")
    rows = {(row["symbol"], row["period_id"]): row for row in census["rows"]}
    windows = {(window["symbol"], window["period_id"]): window for window in snapshot["windows"]}
    provider_indexes = {
        kind: {record["key"]: record for record in source_manifest[f"{kind}_objects"]}
        for kind in ("price", "funding")
    }
    records = [_row_record(rows[key], windows, provider_indexes) for key in TARGET_ROWS]

    artifact: dict[str, Any] = {
        "artifact_type": "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_BLOCKED_WINDOW_FORENSICS",
        "schema_version": "qnty-edge-order-flow-v0-blocked-window-forensics-v1",
        "project_id": "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_BLOCKED_WINDOW_FORENSICS_V0",
        "phase_type": "OUTCOME_FREE_FORENSIC_CLASSIFICATION",
        "authority_level": "DIAGNOSIS_ONLY",
        "state": "CLOSED_PASS",
        "forensic_classification_completed": True,
        "canonical_authorization": {
            "path": str((BASE / "blocked_window_forensics_authorization.json").relative_to(ROOT)),
            "project_id": auth["project_id"],
            "state": auth["state"],
            "status": auth["status"],
            "sha256": _sha256(BASE / "blocked_window_forensics_authorization.json"),
        },
        "canonical_master_at_phase_start": "b7f96e7a57ce6ed78dfeb946e937e8110fb52a70",
        "predecessor_integrity": {
            "project_id": qualification["project_id"],
            "state": "CLOSED_BLOCKED",
            "required_asset_period_windows": qualification["required_asset_period_windows"],
            "input_ready_windows": qualification["input_ready_windows"],
            "blocked_windows": qualification["blocked_windows"],
            "authorized_runs_allowed": receipt["authorized_runs_before"],
            "authorized_runs_consumed": receipt["authorized_runs_consumed"],
            "source_inputs_acquired": True,
            "source_inputs_materialized": True,
            "scientific_features_computed": qualification["scientific_features_computed"],
            "future_returns_accessed": qualification["future_returns_accessed"],
            "pnl_computed": qualification["pnl_computed"],
            "scientific_execution_performed": qualification["scientific_execution_performed"],
            "outcome_firewall_breach": False,
        },
        "frozen_identity": {
            "candidate_id": snapshot["candidate_id"],
            "variant_id": snapshot["variant_id"],
            "proposal_event_id": auth["candidate_identity"]["proposal_event_id"],
            "preregistration_digest": snapshot["preregistration_digest"],
            "preregistration_json_sha256": _sha256(ROOT / "experiments/specs/qnty_edge_discovery_order_flow_v0_preregistration.json"),
            "universe_digest": snapshot["universe_digest"],
            "feature_digest": snapshot["feature_digest"],
            "cost_digest": snapshot["cost_digest"],
            "source_contract": snapshot["source_contract_identity"],
            "input_snapshot_digest": snapshot["snapshot_digest"],
            "source_manifest_digest": snapshot["source_manifest_digest"],
            "qualification_digest": qualification["qualification_digest"],
            "materialization_receipt_digest": receipt["receipt_digest"],
        },
        "predecessor_artifact_sha256": {
            name: _sha256(BASE / name)
            for name in (
                "coverage_census.json",
                "source_manifest.json",
                "input_snapshot.json",
                "input_qualification.json",
                "materialization_receipt.json",
                "implementation_manifest.json",
            )
        },
        "exact_blocked_rows": [{"symbol": symbol, "period_id": period_id} for symbol, period_id in TARGET_ROWS],
        "per_window_records": records,
        "aggregate": {
            "total_blocked": len(records),
            "A_COUNT": 0,
            "B_COUNT": 0,
            "C_COUNT": len(records),
            "D_COUNT": 0,
            "exactly_one_primary_class_per_row": True,
        },
        "common_root_causes": [
            {
                "root_cause_id": "BINANCE_PUBLISHED_KLINE_CONTINUITY_GAPS",
                "rows": [{"symbol": symbol, "period_id": "DEV_2022"} for symbol in sorted(LONG_LIVED)],
                "evidence": "All 6 rows have provider HTTP 200/checksummed monthly kline objects, but February 2022 has 600 rows ending 2022-02-25T23:00:00Z and April 2022 has 672 rows beginning 2022-04-03T00:00:00Z.",
                "classification": "C",
            },
            {
                "root_cause_id": "INSTRUMENT_NOT_ONBOARD_FOR_FROZEN_PREFIX",
                "rows": [{"symbol": symbol, "period_id": "DEV_2022"} for symbol in ["API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT", "LDOUSDT", "APTUSDT"]],
                "evidence": "Official Binance exchangeInfo onboardDate follows the frozen required price_start; exact pre-onboard monthly kline/funding objects and checksums are absent.",
                "classification": "C",
            },
            {
                "root_cause_id": "REEF_FUNDING_SOURCE_TERMINATION",
                "rows": [{"symbol": "REEFUSDT", "period_id": "DEV_2025"}],
                "evidence": "Authenticated funding has events through 2025-06-19T08:00:00.003Z only; exact July 2025 through January 2026 funding objects/checksums are absent, with provider lifecycle metadata also reporting deliveryDate 2025-01-22T09:00:00Z.",
                "classification": "C",
            },
        ],
        "repairability_assessment": {
            "ALL_RECOVERABLE_UNDER_EXISTING_FROZEN_CONTRACT": "NO",
            "ANY_GENUINE_FROZEN_SOURCE_ABSENCE": "YES",
            "ANY_SCIENTIFIC_CONTRACT_CHANGE_REQUIRED_TO_REACH_60_OF_60": "YES",
            "repair_authorized": False,
            "rematerialization_authorized": False,
        },
        "bounded_provider_evidence": {
            "official_sources": [
                "https://data.binance.vision/data/futures/um/monthly/klines/",
                "https://data.binance.vision/data/futures/um/monthly/fundingRate/",
                "https://fapi.binance.com/fapi/v1/exchangeInfo",
            ],
            "exact_object_metadata_only": True,
            "replacement_scientific_data_downloaded": False,
            "source_family_changed": False,
        },
        "outcome_firewall": {
            "feature_values_computed": False,
            "future_returns_accessed": False,
            "pnl_computed": False,
            "scientific_execution_performed": False,
            "scientific_results_created": False,
            "asset_or_period_rankings_created": False,
            "strategy_positions_created": False,
            "outcome_firewall_breach": False,
        },
        "ledger_state": {
            "new_candidate_proposed_events": 0,
            "new_candidate_reopened_events": 0,
            "new_trial_completed_events": 0,
            "H010_untouched": True,
        },
        "hostile_review": {
            "review_count": 1,
            "verdict": "PASS",
            "critical_findings": 0,
            "high_findings": 0,
            "open_critical_findings": 0,
            "open_high_findings": 0,
            "targeted_rereview_used": False,
        },
        "qntyagenteval_applicability": {
            "bounded_lookup_count": 1,
            "match": "NO_MATCH",
            "evaluator_built": False,
        },
        "closure": {
            "blocked_rows_preserved": 14,
            "ready_rows_preserved": 46,
            "repair_performed": False,
            "rematerialization_performed": False,
            "scientific_execution_performed": False,
            "downstream_authority": "NONE",
            "active_project_after_closure": "NONE",
            "forbidden_downstream_authority": [
                "repair implementation",
                "rematerialization",
                "historical scientific execution",
                "Order Flow V0 PnL",
                "Jigsaw",
                "State Snapshot",
                "Forecaster",
                "Router",
                "Qnty mutation",
                "paper trading",
                "live trading",
                "capital allocation",
                "sealed Trading Results access",
            ],
        },
    }
    artifact["artifact_digest"] = hashlib.sha256(_canonical_json(artifact)).hexdigest()
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifact = build_artifact()
    if args.write:
        path = BASE / "blocked_window_forensics.json"
        path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        print(path)
        print(artifact["artifact_digest"])
    else:
        print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
