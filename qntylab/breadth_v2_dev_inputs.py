"""Outcome-free Breadth V2 development-input census coordinator.

This module is deliberately an orchestration boundary.  It enumerates the
frozen registered plan, collapses the two cost modes onto one market-input
unit, derives the exact profile-specific history, and delegates READY bundle
construction to :func:`build_breadth_v2_input_bundle`.  It never calls the
runner, portfolio kernel, strategy functions, or ledger writers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .breadth_v2_input_bundle import InputBundleBlocked, build_breadth_v2_input_bundle, required_history_for_variant
from .breadth_v2_runner import (
    COST_MODES,
    FROZEN_PANEL_ORDER,
    PANEL_EXECUTION_UNIT_ID,
    REGISTERED_PERIODS,
    REGISTERED_SCREEN_ID,
    SINGLE_ASSET,
    SYNCHRONIZED_PANEL,
    enumerate_registered_execution_plan,
    resolve_candidate,
    scientific_cell_count,
)

CONTRACT = "BREADTH_V2_DEV_INPUT_MATERIALIZATION_V0"
FREEZE_T0 = "2026-08-10T19:00:00Z"
TRANSPORT_RETRY_POLICY = "TRANSPORT_RETRY_POLICY_V0"
MAX_TRANSIENT_ATTEMPTS = 3
TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
BLOCKED_SOURCE_STATUSES = frozenset({"SOURCE_OBJECT_ABSENT", "BLOCKED_PRICE_COVERAGE", "BLOCKED_FUNDING_COVERAGE", "BLOCKED_FUNDING_WARMUP", "BLOCKED_PROVENANCE", "BLOCKED_FIXED_PANEL_INPUT", "BLOCKED_PANEL_COVERAGE"})


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def price_clip_range(period_id: str, required_price_closes: int) -> tuple[str, str]:
    """Return the frozen source-open clip ``[T0-Nh, T1-1h]`` inclusive."""
    start, end = REGISTERED_PERIODS[period_id]
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (
        (t0 - timedelta(hours=int(required_price_closes))).isoformat().replace("+00:00", "Z"),
        (t1 - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    )


def funding_parent_start(period_id: str) -> str:
    """Minimum ordinary-funding source start, one hour before evaluation T0."""
    start, _ = REGISTERED_PERIODS[period_id]
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    return (t0 - timedelta(hours=1)).isoformat().replace("+00:00", "Z")


def classify_transport(*, status_code: int | None = None, error: BaseException | None = None) -> str:
    """Classify an unresolved request without turning transport into absence."""
    if status_code in TRANSIENT_HTTP_STATUSES or error is not None:
        return "ACQUISITION_UNRESOLVED"
    if status_code == 404:
        return "SOURCE_OBJECT_ABSENT"
    return "ACQUISITION_UNRESOLVED"


@dataclass(frozen=True)
class MarketInputKey:
    variant_id: str
    candidate_id: str
    family_id: str
    execution_unit_type: str
    execution_unit_id: str
    period_id: str


def enumerate_market_input_plan(candidates_path: str = "experiments/research/candidates.jsonl") -> list[MarketInputKey]:
    """Collapse BASELINE/STRESS descriptors into unique market-input units."""
    descriptors = enumerate_registered_execution_plan(candidates_path)
    grouped: dict[MarketInputKey, set[str]] = {}
    for descriptor in descriptors:
        key = MarketInputKey(
            descriptor.variant_id,
            resolve_candidate(descriptor.variant_id, candidates_path)["candidate_id"],
            descriptor.family_id,
            descriptor.execution_unit_type,
            descriptor.execution_unit_id,
            descriptor.period_id,
        )
        grouped.setdefault(key, set()).add(descriptor.cost_mode)
    if len(grouped) != 996 or any(modes != set(COST_MODES) for modes in grouped.values()):
        raise ValueError("registered plan did not collapse to 996 complete two-cost-mode input units")
    return sorted(grouped, key=lambda key: (key.family_id, key.variant_id, key.execution_unit_type, key.execution_unit_id, key.period_id))


def _symbol_evidence(bundle: Mapping[str, Any], symbol: str, price_sources: Mapping[str, Mapping[str, Any]], funding_sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    asset = bundle["bundle_payload"]["assets"][symbol]
    funding_manifest = funding_sources[symbol].get("manifest", {})
    return {
        "price_parent_normalized_sha256": asset["price_parent_content"],
        "price_provenance_digest": asset["price_provenance"],
        "funding_parent_normalized_sha256": asset["funding_parent_content"],
        "funding_archive_provenance_digest": asset["funding_provenance"],
        "funding_rest_witness_digest": funding_manifest.get("rest_coverage_witness_digest"),
        "funding_reconciliation_digest": funding_manifest.get("coverage_reconciliation_digest"),
        "coverage_status": asset["coverage"],
    }


def materialize_market_input(key: MarketInputKey, *, price_sources: Mapping[str, Mapping[str, Any]], funding_sources: Mapping[str, Mapping[str, Any]], candidates_path: str = "experiments/research/candidates.jsonl") -> dict[str, Any]:
    """Build one census row, with no strategy execution or outcome fields."""
    candidate = resolve_candidate(key.variant_id, candidates_path)
    history = required_history_for_variant(key.family_id, candidate["parameters"])
    start, end = REGISTERED_PERIODS[key.period_id]
    symbols = [key.execution_unit_id] if key.execution_unit_type == SINGLE_ASSET else list(FROZEN_PANEL_ORDER)
    base = {**asdict(key), "mapped_cost_modes": sorted(COST_MODES), "required_price_closes": history["required_price_closes"], "required_funding_signal_events": history["required_funding_signal_events"], "price_source_range": list(price_clip_range(key.period_id, history["required_price_closes"])), "funding_source_range": [funding_parent_start(key.period_id), end], "status": "BLOCKED", "evaluation_input_bundle_sha256": None, "blocking_reason": None, "blocking_details": None, "per_symbol_evidence_summary": {}}
    try:
        bundle = build_breadth_v2_input_bundle(evaluation_start=start, evaluation_end=end, symbols=symbols, price_sources=price_sources, funding_sources=funding_sources, family=key.family_id, parameters=candidate["parameters"])
    except InputBundleBlocked as exc:
        base["blocking_reason"], base["blocking_details"] = exc.status, str(exc)
        return base
    base.update({"status": "READY", "evaluation_input_bundle_sha256": bundle["evaluation_input_bundle_sha256"], "per_symbol_evidence_summary": {symbol: _symbol_evidence(bundle, symbol, price_sources, funding_sources) for symbol in symbols}})
    return base


def build_census(rows: Sequence[Mapping[str, Any]], *, freeze_commit: str, candidates_path: str = "experiments/research/candidates.jsonl") -> dict[str, Any]:
    """Build deterministic global counts and the content-addressed census."""
    ordered = sorted((dict(row) for row in rows), key=lambda row: tuple(row[name] for name in ("family_id", "variant_id", "execution_unit_type", "execution_unit_id", "period_id")))
    if len(ordered) != 996 or len({(row["variant_id"], row["execution_unit_type"], row["execution_unit_id"], row["period_id"]) for row in ordered}) != 996:
        raise ValueError("census must contain exactly 996 unique input records")
    if any(row["status"] == "READY" and not row.get("evaluation_input_bundle_sha256") for row in ordered):
        raise ValueError("READY census row lacks bundle identity")
    if any(row["status"] == "BLOCKED" and row.get("evaluation_input_bundle_sha256") is not None for row in ordered):
        raise ValueError("BLOCKED census row has fabricated bundle identity")
    ready = sum(row["status"] == "READY" for row in ordered)
    mapped_exec = ready * 2
    blocked_exec = (996 - ready) * 2
    ready_cells = sum(1 if row["execution_unit_type"] == SINGLE_ASSET else len(FROZEN_PANEL_ORDER) for row in ordered if row["status"] == "READY")
    blocked_cells = scientific_cell_count() - ready_cells
    manifest = {"contract": CONTRACT, "registered_screen_id": REGISTERED_SCREEN_ID, "instrument_contract_id": "BINANCE_USDM_PERPETUAL_USDT_V1", "pre_acquisition_freeze_commit": freeze_commit, "sealed_t0": FREEZE_T0, "registered_input_records": 996, "registered_execution_units": 1992, "registered_scientific_cells": 3360, "ready_input_records": ready, "blocked_input_records": 996 - ready, "ready_mapped_execution_units": mapped_exec, "blocked_mapped_execution_units": blocked_exec, "ready_mapped_scientific_cells": ready_cells, "blocked_mapped_scientific_cells": blocked_cells, "acquisition_unresolved_count": sum(row.get("blocking_reason") == "ACQUISITION_UNRESOLVED" for row in ordered), "input_records": ordered}
    manifest["campaign_input_universe_sha256"] = _sha({key: value for key, value in manifest.items() if key != "campaign_input_universe_sha256"})
    return manifest
