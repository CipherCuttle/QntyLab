"""Frozen execution/readiness seam for the Qnty trading-results sprint.

This module is deliberately narrower than a general evaluator.  It consumes
the already-frozen candidate-selection artifact, delegates strategy and
economic arithmetic to the existing Breadth V2 runner/kernel, and exposes a
single maturity-gated adjudication entry point.  It does not acquire data,
append ledger events, mutate Qnty, or access the sealed-forward window during
the active horizon.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .breadth_v2_runner import (
    COST_MODES,
    FROZEN_PANEL_ORDER,
    SINGLE_ASSET,
    _single_asset_cell,
    execute_candidate_and_benchmark,
)
from .breadth_v2_sealed import (
    EARLIEST_ELIGIBLE_ADJUDICATION_TIME,
    SEALED_T0,
    enforce_sealed_adjudication_authorized,
)

FREEZE_PATH = Path("experiments/specs/qnty_trading_results_sprint_v0_candidate_selection.json")
EXPECTED_FREEZE_SHA256 = "91c3ccd147b6fe5e19e0851834ea601dc90acf0d60f5c942aca13de4d37d5e11"
READINESS_CONTRACT_ID = "QNTY_TRADING_RESULTS_SPRINT_V0_EXECUTION_READINESS_V0"
FORWARD_END = "2026-11-08T19:00:00Z"
EXPECTED_FORWARD_BOUNDARY_COUNT = 2161  # 2,160 one-hour returns.
EXPECTED_EXECUTION_COUNT_PER_CANDIDATE = 40
EXPECTED_TOTAL_EXECUTION_COUNT = 120
EXPECTED_COST_MODES = ("BASELINE_EXECUTION", "STRESS_EXECUTION")
EXPECTED_CANDIDATE_IDS = (
    "CANDIDATE_BREADTH_V2_MA_24_96",
    "CANDIDATE_BREADTH_V2_BREAKOUT_72",
    "CANDIDATE_BREADTH_V2_BREAKOUT_168",
)


class ReadinessBlocked(RuntimeError):
    """Raised when a frozen identity or execution contract is violated."""


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha(value: Any) -> str:
    return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def freeze_artifact_sha256(path: Path = FREEZE_PATH) -> str:
    return _sha_bytes(path.read_bytes())


def load_freeze(path: Path = FREEZE_PATH) -> dict[str, Any]:
    """Load and validate the exact three-candidate selection artifact."""
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessBlocked(f"cannot load candidate freeze: {path}") from exc
    if freeze_artifact_sha256(path) != EXPECTED_FREEZE_SHA256:
        raise ReadinessBlocked("candidate-freeze digest differs from the canonical frozen selection")
    if artifact.get("artifact_type") != "QNTY_TRADING_RESULTS_SPRINT_V0_CANDIDATE_SELECTION":
        raise ReadinessBlocked("wrong candidate-freeze artifact type")
    if artifact.get("status") != "FROZEN_FOR_SUBSEQUENT_EXECUTION_ONLY":
        raise ReadinessBlocked("candidate freeze is not execution-only and frozen")
    if artifact.get("execution_in_this_phase") is not False:
        raise ReadinessBlocked("candidate freeze permits execution in the selection phase")
    candidates = artifact.get("candidates")
    if artifact.get("selected_candidate_count") != 3 or not isinstance(candidates, list):
        raise ReadinessBlocked("candidate freeze does not contain exactly three candidates")
    if tuple(row.get("candidate_id") for row in candidates) != EXPECTED_CANDIDATE_IDS:
        raise ReadinessBlocked("candidate order or identity differs from the frozen selection")
    if len({row.get("variant_id") for row in candidates}) != 3:
        raise ReadinessBlocked("candidate variants are not unique")
    contract = artifact.get("evaluation_contract", {})
    future = contract.get("future_execution_window", {})
    if future.get("sealed_t0") != SEALED_T0.strftime("%Y-%m-%dT%H:%M:%SZ") or future.get("end") != FORWARD_END:
        raise ReadinessBlocked("forward window differs from the frozen selection contract")
    if future.get("minimum_complete_hours") != 2160:
        raise ReadinessBlocked("forward horizon differs from the frozen selection contract")
    if contract.get("assets_universe", {}).get("symbols") != list(FROZEN_PANEL_ORDER):
        raise ReadinessBlocked("forward universe differs from the frozen Breadth V2 panel")
    costs = contract.get("costs", {})
    if tuple(key for key in costs if key in EXPECTED_COST_MODES) != EXPECTED_COST_MODES:
        raise ReadinessBlocked("frozen cost modes are missing or reordered")
    return artifact


def candidate_freeze_digest(path: Path = FREEZE_PATH) -> str:
    load_freeze(path)
    return freeze_artifact_sha256(path)


def candidate_records(freeze: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    rows = tuple(freeze["candidates"])
    if tuple(row["candidate_id"] for row in rows) != EXPECTED_CANDIDATE_IDS:
        raise ReadinessBlocked("candidate records do not match the frozen three-candidate set")
    return rows


def build_forward_execution_plan(freeze: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the deterministic, data-free 120-cell forward execution plan."""
    rows: list[dict[str, Any]] = []
    for candidate in candidate_records(freeze):
        for symbol in FROZEN_PANEL_ORDER:
            for cost_mode in EXPECTED_COST_MODES:
                rows.append({
                    "candidate_id": candidate["candidate_id"],
                    "variant_id": candidate["variant_id"],
                    "family": candidate["family"],
                    "parameters": dict(candidate["parameters"]),
                    "execution_unit_type": SINGLE_ASSET,
                    "execution_unit_id": symbol,
                    "period_id": "SEALED_FORWARD_2026_08_10_2026_11_08",
                    "cost_mode": cost_mode,
                    "evaluation_start": SEALED_T0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "evaluation_end": FORWARD_END,
                })
    if len(rows) != EXPECTED_TOTAL_EXECUTION_COUNT:
        raise ReadinessBlocked(f"forward plan count mismatch: {len(rows)}")
    return rows


def _required_history(candidate: Mapping[str, Any]) -> dict[str, int]:
    family = candidate["family"]
    parameters = candidate["parameters"]
    if family == "MOVING_AVERAGE_TREND":
        return {"required_price_closes": int(parameters["slow"]), "required_funding_signal_events": 0}
    if family == "PRICE_BREAKOUT":
        return {"required_price_closes": int(parameters["lookback"]) + 1, "required_funding_signal_events": 0}
    raise ReadinessBlocked(f"unsupported frozen candidate family: {family}")


def _validate_bundle_identity(candidate: Mapping[str, Any], bundle: Mapping[str, Any]) -> str | None:
    """Return a coverage block reason, or ``None`` for a structurally ready bundle.

    Identity errors are hard blocks.  Coverage errors become a candidate KILL
    record later so the frozen denominator is not silently deleted.
    """
    if not isinstance(bundle, Mapping):
        raise ReadinessBlocked("candidate input bundle is not a mapping")
    payload = bundle.get("bundle_payload")
    if not isinstance(payload, Mapping):
        raise ReadinessBlocked("candidate input bundle has no payload")
    if payload.get("contract") != "BREADTH_V2_INPUT_BUNDLE_V0":
        raise ReadinessBlocked("candidate input bundle contract mismatch")
    if payload.get("instrument_contract_id") != "BINANCE_USDM_PERPETUAL_USDT_V1":
        raise ReadinessBlocked("candidate input bundle instrument contract mismatch")
    if payload.get("symbols") != list(FROZEN_PANEL_ORDER):
        raise ReadinessBlocked("candidate input bundle universe mismatch")
    boundaries = payload.get("boundaries")
    expected = [
        (SEALED_T0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in range(EXPECTED_FORWARD_BOUNDARY_COUNT)
    ]
    if boundaries != expected:
        raise ReadinessBlocked("candidate input bundle must contain the complete 2,160-hour boundary grid")
    if bundle.get("evaluation_input_bundle_sha256") != _recompute_bundle_digest(payload):
        raise ReadinessBlocked("candidate input bundle digest mismatch")
    required = bundle.get("required_history")
    if required != _required_history(candidate):
        raise ReadinessBlocked("candidate input bundle warmup identity mismatch")
    if bundle.get("status") != "READY":
        return f"input bundle status: {bundle.get('status')}"
    if set(bundle.get("admitted_price", {})) != set(FROZEN_PANEL_ORDER) or set(bundle.get("admitted_funding", {})) != set(FROZEN_PANEL_ORDER):
        return "missing required asset price or funding source"
    for symbol in FROZEN_PANEL_ORDER:
        asset = payload.get("assets", {}).get(symbol, {})
        if asset.get("coverage") != "COMPLETE":
            return f"incomplete coverage for {symbol}"
        if not bundle["admitted_price"].get(symbol) or not bundle["admitted_funding"].get(symbol):
            return f"missing admitted price or funding rows for {symbol}"
    return None


def _recompute_bundle_digest(payload: Mapping[str, Any]) -> str:
    from .breadth_v2_execution import evaluation_input_bundle_sha256

    return evaluation_input_bundle_sha256(
        instrument_contract_id=payload["instrument_contract_id"],
        symbols=payload["symbols"],
        boundaries=payload["boundaries"],
        decision_clock=payload["decision_clock"],
        assets=payload["assets"],
    )


def validate_forward_inputs(freeze: Mapping[str, Any], bundles_by_candidate: Mapping[str, Mapping[str, Any]]) -> dict[str, str | None]:
    """Validate candidate-specific forward bundle identities without execution."""
    candidates = candidate_records(freeze)
    if set(bundles_by_candidate) != set(EXPECTED_CANDIDATE_IDS):
        raise ReadinessBlocked("forward input mapping must contain exactly the three frozen candidates")
    return {
        candidate["candidate_id"]: _validate_bundle_identity(candidate, bundles_by_candidate[candidate["candidate_id"]])
        for candidate in candidates
    }


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _metric_mean(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows]
    return sum(values) / len(values) if values else None


def reduce_candidate(*, candidate: Mapping[str, Any], cells: Sequence[Mapping[str, Any]], blocked_reason: str | None = None) -> dict[str, Any]:
    """Reduce one exact candidate's 20×2 cells under the frozen gates."""
    expected = len(FROZEN_PANEL_ORDER) * len(EXPECTED_COST_MODES)
    errors: list[str] = []
    if blocked_reason:
        errors.append(blocked_reason)
    if len(cells) != expected:
        errors.append("incomplete_candidate_cells")
    keys = {(row.get("symbol"), row.get("cost_mode")) for row in cells}
    expected_keys = {(symbol, cost) for symbol in FROZEN_PANEL_ORDER for cost in EXPECTED_COST_MODES}
    if keys != expected_keys or len(keys) != len(cells):
        errors.append("candidate_cell_identity_mismatch")
    for row in cells:
        for key in ("candidate_net_return", "benchmark_net_return", "excess_return_vs_benchmark", "gross_return", "turnover", "trade_count", "exposure_fraction", "fee_cost", "slippage_cost", "funding_cost", "price_pnl"):
            if key in row and not _finite(row[key]):
                errors.append("nonfinite_metric")
    baseline = [row for row in cells if row.get("cost_mode") == "BASELINE_EXECUTION"]
    stress = [row for row in cells if row.get("cost_mode") == "STRESS_EXECUTION"]
    baseline_excess = _metric_mean(baseline, "excess_return_vs_benchmark") if len(baseline) == 20 else None
    stress_excess = _metric_mean(stress, "excess_return_vs_benchmark") if len(stress) == 20 else None
    stress_net = _metric_mean(stress, "candidate_net_return") if len(stress) == 20 else None
    baseline_net = _metric_mean(baseline, "candidate_net_return") if len(baseline) == 20 else None
    positive_assets = sum(float(row["excess_return_vs_benchmark"]) > 0 for row in stress)
    positive_support = sum(float(row["excess_return_vs_benchmark"]) for row in stress if float(row["excess_return_vs_benchmark"]) > 0)
    max_positive_share = max(
        (float(row["excess_return_vs_benchmark"]) / positive_support for row in stress if float(row["excess_return_vs_benchmark"]) > 0),
        default=None,
    )
    cost_retention = stress_excess / baseline_excess if baseline_excess is not None and baseline_excess > 0 and stress_excess is not None else None
    gates = {
        "integrity": "FAIL" if errors else "PASS",
        "stress_aggregate": "PASS" if stress_excess is not None and stress_excess > 0 else "FAIL",
        "stress_forward_non_negative": "PASS" if stress_excess is not None and stress_excess >= 0 else "FAIL",
        "stress_asset_breadth": "PASS" if positive_assets >= 10 else "FAIL",
        "concentration": "PASS" if max_positive_share is not None and max_positive_share <= 0.35 else "FAIL",
        "cost_survival": "PASS" if cost_retention is not None and cost_retention >= 0.50 else "FAIL",
        "fixed_parameter_identity": "PASS",
    }
    hard_failure = any(value == "FAIL" for value in gates.values())
    decision = "KILL" if hard_failure else "PROMOTE"
    return {
        "candidate_id": candidate["candidate_id"],
        "variant_id": candidate["variant_id"],
        "family": candidate["family"],
        "parameters": dict(candidate["parameters"]),
        "window": {"start": SEALED_T0.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": FORWARD_END, "complete_hours": 2160},
        "cell_count": len(cells),
        "metrics": {
            "candidate_net_return": stress_net,
            "benchmark_excess_return": stress_excess,
            "annualized_volatility": None,
            "sharpe_like_return_over_volatility": None,
            "maximum_drawdown": None,
            "positive_asset_breadth": positive_assets,
            "baseline_benchmark_excess_return": baseline_excess,
            "stress_benchmark_excess_return": stress_excess,
            "baseline_candidate_net_return": baseline_net,
            "stress_candidate_net_return": stress_net,
            "stress_positive_asset_breadth": positive_assets,
            "stress_positive_support": positive_support,
            "stress_max_positive_asset_share": max_positive_share,
            "cost_retention_ratio": cost_retention,
            "cost_delta": None if baseline_net is None or stress_net is None else stress_net - baseline_net,
        },
        "asset_window_cost_cells": [dict(row) for row in cells],
        "regime_decomposition": {},
        "selection_evidence_context": {
            "is_unseen_confirmation": False,
            "family_status": candidate["prior_evidence"]["family_status"],
            "variant_stress_excess": candidate["prior_evidence"]["variant_stress_excess"],
            "variant_stress_net": candidate["prior_evidence"]["variant_stress_net"],
            "parameter_sensitivity": "SELECTION_CONTEXT_ONLY; no neighbors executed",
        },
        "gates": gates,
        "reason_codes": sorted(set(errors)),
        "decision": decision,
    }


def _execute_candidate(candidate: Mapping[str, Any], bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one candidate against one already-validated bundle."""
    cells: list[dict[str, Any]] = []
    curves: dict[str, list[list[float]]] = {cost: [] for cost in EXPECTED_COST_MODES}
    try:
        for symbol in FROZEN_PANEL_ORDER:
            for cost_mode in EXPECTED_COST_MODES:
                costs = COST_MODES[cost_mode]
                candidate_result, benchmark_result, _ = execute_candidate_and_benchmark(
                    family_id=candidate["family"], variant_id=candidate["variant_id"], parameters=candidate["parameters"],
                    execution_unit_type=SINGLE_ASSET, execution_unit_id=symbol, input_bundle=bundle,
                    fee_bps=costs["fee_bps"], slippage_bps=costs["slippage_bps"],
                )
                row = dict(_single_asset_cell(symbol, candidate_result, benchmark_result))
                row.update({
                    "cost_mode": cost_mode,
                    "gross_return": (row["price_pnl"] + row["funding_pnl"]) / candidate_result.initial_equity,
                    "trade_count": sum(1 for path_row in candidate_result.boundary_path if path_row["turnover"] > 0.0),
                    "funding_cost": -row["funding_pnl"],
                })
                cells.append(row)
                curve = [candidate_result.initial_equity] + [float(path_row["equity_after_rebalance"]) for path_row in candidate_result.boundary_path]
                curve[-1] = float(candidate_result.boundary_path[-1]["final_equity"])
                curves[cost_mode].append([value / candidate_result.initial_equity for value in curve])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return reduce_candidate(candidate=candidate, cells=[], blocked_reason=f"execution_input_or_funding_blocked:{exc}")
    result = reduce_candidate(candidate=candidate, cells=cells)
    for cost_mode, rows in curves.items():
        if not rows:
            continue
        aggregate_curve = [sum(row[index] for row in rows) / len(rows) for index in range(len(rows[0]))]
        hourly_returns = [aggregate_curve[index] / aggregate_curve[index - 1] - 1.0 for index in range(1, len(aggregate_curve)) if aggregate_curve[index - 1] != 0]
        mean_return = sum(hourly_returns) / len(hourly_returns) if hourly_returns else 0.0
        variance = sum((value - mean_return) ** 2 for value in hourly_returns) / len(hourly_returns) if hourly_returns else 0.0
        volatility = math.sqrt(variance) * math.sqrt(24 * 365)
        result.setdefault("regime_decomposition", {})[f"SEALED_FORWARD_FULL_WINDOW:{cost_mode}"] = {
            "annualized_volatility": volatility,
            "sharpe_like_return_over_volatility": (mean_return / math.sqrt(variance) * math.sqrt(24 * 365)) if variance else None,
            "maximum_drawdown": min((value / max(aggregate_curve[:index + 1]) - 1.0) for index, value in enumerate(aggregate_curve)) if aggregate_curve else None,
        }
        if cost_mode == "STRESS_EXECUTION":
            result["metrics"].update(result["regime_decomposition"][f"SEALED_FORWARD_FULL_WINDOW:{cost_mode}"])
    return result


def adjudicate(*, as_of: datetime, freeze: Mapping[str, Any], bundles_by_candidate: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Maturity-gated forward adjudication; never callable before maturity."""
    # This must be the first operation that could lead to forward input access.
    enforce_sealed_adjudication_authorized(as_of)
    canonical_freeze = load_freeze()
    if freeze != canonical_freeze:
        raise ReadinessBlocked("adjudication input is not the canonical candidate freeze")
    freeze = canonical_freeze
    coverage = validate_forward_inputs(freeze, bundles_by_candidate)
    results = []
    for candidate in candidate_records(freeze):
        blocked = coverage[candidate["candidate_id"]]
        results.append(
            reduce_candidate(candidate=candidate, cells=[], blocked_reason=blocked)
            if blocked else _execute_candidate(candidate, bundles_by_candidate[candidate["candidate_id"]])
        )
    return {
        "contract_id": READINESS_CONTRACT_ID,
        "candidate_freeze_digest": candidate_freeze_digest(),
        "adjudication_authorized_at": EARLIEST_ELIGIBLE_ADJUDICATION_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
    }


def implementation_source_manifest(repo_root: Path = Path(".")) -> dict[str, Any]:
    """Return the immutable source identity to record before forward access."""
    paths = (
        "qntylab/qnty_trading_results_sprint_v0_execution.py",
        "qntylab/breadth_v2_runner.py",
        "qntylab/breadth_v2_execution.py",
        "qntylab/breadth_v2_strategies.py",
        "qntylab/breadth_v2_input_bundle.py",
        "qntylab/breadth_v2_path.py",
        "qntylab/breadth_v2_sealed.py",
        "qntylab/instrument_contract.py",
    )
    rows = [{"path": path, "sha256": _sha_bytes((repo_root / path).read_bytes())} for path in paths]
    return {"source_paths": rows, "implementation_sha256": _canonical_sha(rows)}
