from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .focused_trend_validation import expand_planned_holdout_runs
from .research_ledger import COMPACT_METRIC_KEYS, canonical_bytes, load_canonical_history, verify_indexes_current
from .strategy_test import _strategy_warmup_bars, sha256_path, validate_normalization_provenance


SPEC_PATH = Path("experiments/specs/focused_trend_validation_v1.json")
RUNS_DIR = Path("experiments/runs/focused_trend_validation_v1/2023_holdout")
SUMMARY_DIR = Path("experiments/research/summaries")
CELLS_PATH = SUMMARY_DIR / "focused_trend_validation_v1_2023_holdout_cells.csv"
VARIANTS_PATH = SUMMARY_DIR / "focused_trend_validation_v1_2023_holdout_variants.csv"
JSON_PATH = SUMMARY_DIR / "focused_trend_validation_v1_2023_holdout_review.json"
MD_PATH = SUMMARY_DIR / "focused_trend_validation_v1_2023_holdout_review.md"

PRIMARY_METRIC = "excess_return_vs_buy_and_hold"

CELL_FIELDS = (
    "trial_id",
    "candidate_id",
    "variant_id",
    "family",
    "parameters_json",
    "symbol",
    "period_id",
    "cost_mode",
    "fee_bps",
    "slippage_bps",
    "input_sha256",
    "receipt_sha256",
    "observation_count",
    "trade_count",
    "exposure_fraction",
    "gross_return",
    "net_return",
    "buy_and_hold_return",
    "excess_return_vs_buy_and_hold",
    "total_cost",
    "maximum_drawdown",
    "primary_metric_name",
    "primary_metric_value",
    "primary_positive",
    "receipt_valid",
    "normalization_provenance_valid",
)

VARIANT_FIELDS = (
    "candidate_id",
    "variant_id",
    "family",
    "parameters_json",
    "trial_count",
    "completed_trial_count",
    "integrity_failure_count",
    "baseline_primary_by_asset",
    "stress_primary_by_asset",
    "baseline_primary_aggregate",
    "stress_primary_aggregate",
    "baseline_positive_asset_count",
    "stress_positive_asset_count",
    "baseline_trade_count_total",
    "stress_trade_count_total",
    "baseline_total_cost",
    "stress_total_cost",
    "baseline_maximum_drawdown_worst",
    "stress_maximum_drawdown_worst",
    "aggregate_stress_positive",
    "stress_asset_breadth_pass",
    "completion_gate_pass",
    "integrity_gate_pass",
    "mechanical_holdout_gate_pass",
    "failure_reasons",
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite output")
        return repr(value)
    if isinstance(value, (dict, list, tuple)):
        return _json_dumps(value)
    return str(value)


def _finite_number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"non-finite numeric value at {path}")
    return float(value)


def _events_by_trial(root: Path, planned: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    wanted_variants = {row["variant_id"] for row in planned}
    period_start = {row["config"]["evaluation_start"] for row in planned}
    period_end = {row["config"]["evaluation_end"] for row in planned}
    if len(period_start) != 1 or len(period_end) != 1:
        raise ValueError("ambiguous focused holdout period")
    history = load_canonical_history(root / "experiments/research")
    focused = [
        event
        for event in history.trials
        if event["variant_id"] in wanted_variants
        and event["evaluation_start"] in period_start
        and event["evaluation_end"] in period_end
    ]
    by_trial: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in focused:
        by_trial[event["trial_id"]].append(event)
    return by_trial, focused


def _run_artifacts(root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    receipts: dict[str, Path] = {}
    metrics: dict[str, Path] = {}
    for path in sorted((root / RUNS_DIR).glob("*/run_receipt.json")):
        receipt = _load_json(path)
        trial_id = receipt["trial_id"]
        if trial_id in receipts:
            raise ValueError(f"duplicate receipt trial_id: {trial_id}")
        receipts[trial_id] = path
        metrics[trial_id] = path.parent / "metrics.json"
    return receipts, metrics


def _expected_cost_mode(fee_bps: float, slippage_bps: float, spec: dict[str, Any]) -> str:
    for name, costs in spec["cost_modes"].items():
        if float(costs["fee_bps"]) == fee_bps and float(costs["slippage_bps"]) == slippage_bps:
            return name
    raise ValueError(f"unexpected cost assumptions: fee={fee_bps} slippage={slippage_bps}")


def _validate_warmup(receipt: dict[str, Any]) -> bool:
    required = _strategy_warmup_bars(receipt["strategy_id"], receipt["parameters"])
    actual = int(receipt["warmup_range"]["observation_count"])
    return actual == required


def _validate_receipt(
    *,
    root: Path,
    plan: dict[str, Any],
    event: dict[str, Any],
    receipt_path: Path,
    metrics_path: Path,
    receipt: dict[str, Any],
    metrics: dict[str, Any],
    spec: dict[str, Any],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    receipt_sha = sha256_path(receipt_path)
    metrics_sha = sha256_path(metrics_path)
    variant = next(item for item in spec["variants"] if item["variant_id"] == plan["variant_id"])
    checks = {
        "event_receipt_sha": event["receipt_sha256"] == receipt_sha,
        "receipt_metrics_sha": receipt["result_artifact_sha256"]["metrics"] == metrics_sha,
        "compact_metrics": event["compact_metrics"] == {key: metrics[key] for key in sorted(COMPACT_METRIC_KEYS) if key in metrics},
        "trial_id": receipt["trial_id"] == event["trial_id"] == plan["trial_id"],
        "candidate_id": receipt["candidate_id"] == event["candidate_id"] == plan["candidate_id"],
        "variant_id": receipt["variant_id"] == event["variant_id"] == plan["variant_id"],
        "family_id": receipt["family_id"] == event["family_id"] == variant["family_id"],
        "strategy_id": receipt["strategy_id"] == variant["strategy_id"],
        "parameters": receipt["parameters"] == variant["parameters"],
        "research_intent": receipt["research_intent"] == event["research_intent"] == "FOLLOW_UP",
        "symbol": receipt["symbol"] == event["symbol"] == plan["asset"],
        "evaluation_start": receipt["evaluation_range"]["start"] == event["evaluation_start"] == plan["config"]["evaluation_start"],
        "evaluation_end": receipt["evaluation_range"]["end"] == event["evaluation_end"] == plan["config"]["evaluation_end"],
        "input_sha256": receipt["input_sha256"] == event["input_sha256"] == plan["input_sha256"],
        "fee_bps": float(receipt["fee_assumption"]["fee_bps"]) == float(event["fee_bps"]) == float(plan["config"]["fee_bps"]),
        "slippage_bps": float(receipt["slippage_assumption"]["slippage_bps"]) == float(event["slippage_bps"]) == float(plan["config"]["slippage_bps"]),
        "cost_mode": _expected_cost_mode(float(event["fee_bps"]), float(event["slippage_bps"]), spec) == plan["cost_mode"],
        "gap_policy": receipt["gap_policy"] == event["gap_policy"] == "REJECT",
        "expected_interval": receipt["expected_interval"] == event["expected_interval"] == "1h",
        "status": receipt["status"] == "completed",
        "exploratory_only": receipt["exploratory_only"] is True,
        "warmup": _validate_warmup(receipt),
    }
    failures.extend(name for name, ok in checks.items() if not ok)
    try:
        validate_normalization_provenance(
            provenance=receipt.get("normalization_provenance"),
            normalized_input=(root / plan["config"]["input_path"]).resolve(),
            input_sha256=plan["input_sha256"],
            config_path=root / SPEC_PATH,
        )
    except Exception as exc:  # noqa: BLE001 - collect integrity evidence deterministically.
        failures.append(f"normalization_provenance:{exc}")
    return not failures, failures


def _integrity_overview(
    *,
    planned: list[dict[str, Any]],
    focused_events: list[dict[str, Any]],
    by_trial: dict[str, list[dict[str, Any]]],
    receipts: dict[str, Path],
    metrics: dict[str, Path],
    integrity_failures: dict[str, list[str]],
) -> dict[str, Any]:
    planned_ids = [row["trial_id"] for row in planned]
    planned_set = set(planned_ids)
    event_ids = [event["trial_id"] for event in focused_events]
    duplicate_events = sorted(trial_id for trial_id, count in Counter(event_ids).items() if count > 1)
    return {
        "expected_trials": len(planned),
        "completed_expected_trials": sum(1 for trial_id in planned_set if len(by_trial.get(trial_id, [])) == 1),
        "missing": sorted(planned_set - set(event_ids)),
        "duplicates": duplicate_events,
        "unexpected": sorted(set(event_ids) - planned_set),
        "failed": sorted(trial_id for trial_id, failures in integrity_failures.items() if failures),
        "receipt_validation": f"{sum(1 for trial_id in planned_set if trial_id in receipts)}/{len(planned)}",
        "normalization_provenance": f"{sum(1 for failures in integrity_failures.values() if not any(item.startswith('normalization_provenance:') for item in failures))}/{len(planned)}",
        "required_finite_metrics": f"{sum(1 for trial_id in planned_set if trial_id in metrics)}/{len(planned)}",
        "per_variant": dict(sorted(Counter(row["variant_id"] for row in planned).items())),
        "per_asset": dict(sorted(Counter(row["asset"] for row in planned).items())),
        "per_cost_mode": dict(sorted(Counter(row["cost_mode"] for row in planned).items())),
    }


def _by_asset(rows: list[dict[str, Any]], cost_mode: str) -> dict[str, float]:
    return {row["symbol"]: float(row["primary_metric_value"]) for row in rows if row["cost_mode"] == cost_mode}


def _sum_metric(rows: list[dict[str, Any]], cost_mode: str) -> float:
    return float(sum(float(row["primary_metric_value"]) for row in rows if row["cost_mode"] == cost_mode))


def _variant_rows(spec: dict[str, Any], cells: list[dict[str, Any]], integrity_failures: dict[str, list[str]]) -> list[dict[str, Any]]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        by_variant[cell["variant_id"]].append(cell)
    result: list[dict[str, Any]] = []
    gate = spec["tracks"]["A_untouched_2023_holdout"]["continuation_gate"]
    if gate["aggregate_stressed_primary_result_positive"] is not True:
        raise ValueError("BLOCKED_BY_HOLDOUT_AGGREGATION_AMBIGUITY")
    for variant in spec["variants"]:
        rows = by_variant[variant["variant_id"]]
        baseline = [row for row in rows if row["cost_mode"] == "baseline"]
        stress = [row for row in rows if row["cost_mode"] == "stress"]
        baseline_by_asset = _by_asset(rows, "baseline")
        stress_by_asset = _by_asset(rows, "stress")
        baseline_aggregate = _sum_metric(rows, "baseline")
        stress_aggregate = _sum_metric(rows, "stress")
        completion_pass = len(rows) == 6
        integrity_count = len(integrity_failures[variant["variant_id"]])
        integrity_pass = integrity_count == int(gate["integrity_failures_allowed"])
        aggregate_pass = stress_aggregate > 0
        breadth_count = sum(1 for value in stress_by_asset.values() if value > 0)
        breadth_pass = breadth_count >= int(gate["minimum_stressed_primary_positive_asset_count"])
        reasons: list[str] = []
        if not completion_pass:
            reasons.append("COMPLETION_GATE_FAIL")
        if not integrity_pass:
            reasons.append("INTEGRITY_GATE_FAIL")
        if not aggregate_pass:
            reasons.append("AGGREGATE_STRESS_GATE_FAIL")
        if not breadth_pass:
            reasons.append("STRESS_ASSET_BREADTH_GATE_FAIL")
        result.append(
            {
                "candidate_id": variant["candidate_id"],
                "variant_id": variant["variant_id"],
                "family": variant["family_id"],
                "parameters_json": variant["parameters"],
                "trial_count": 6,
                "completed_trial_count": len(rows),
                "integrity_failure_count": integrity_count,
                "baseline_primary_by_asset": baseline_by_asset,
                "stress_primary_by_asset": stress_by_asset,
                "baseline_primary_aggregate": baseline_aggregate,
                "stress_primary_aggregate": stress_aggregate,
                "baseline_positive_asset_count": sum(1 for value in baseline_by_asset.values() if value > 0),
                "stress_positive_asset_count": breadth_count,
                "baseline_trade_count_total": int(sum(int(row["trade_count"]) for row in baseline)),
                "stress_trade_count_total": int(sum(int(row["trade_count"]) for row in stress)),
                "baseline_total_cost": float(sum(float(row["total_cost"]) for row in baseline)),
                "stress_total_cost": float(sum(float(row["total_cost"]) for row in stress)),
                "baseline_maximum_drawdown_worst": min(float(row["maximum_drawdown"]) for row in baseline),
                "stress_maximum_drawdown_worst": min(float(row["maximum_drawdown"]) for row in stress),
                "aggregate_stress_positive": aggregate_pass,
                "stress_asset_breadth_pass": breadth_pass,
                "completion_gate_pass": completion_pass,
                "integrity_gate_pass": integrity_pass,
                "mechanical_holdout_gate_pass": completion_pass and integrity_pass and aggregate_pass and breadth_pass,
                "failure_reasons": reasons,
            }
        )
    return result


def _state_by_variant(root: Path) -> dict[str, str]:
    state, _, _ = verify_indexes_current(root / "experiments/research")
    return {variant_id: row["status"] for variant_id, row in state["variants"].items()}


def _proposed_decisions(variants: list[dict[str, Any]], states: dict[str, str]) -> list[dict[str, Any]]:
    decisions = []
    for row in variants:
        if row["mechanical_holdout_gate_pass"]:
            proposed = "FOLLOW_UP"
            reason = "PASSED_2023_HOLDOUT_GATE_PENDING_FORWARD_AND_DISTINCTNESS"
        elif row["completion_gate_pass"] and row["integrity_gate_pass"]:
            proposed = "GRAVEYARDED"
            agg_fail = not row["aggregate_stress_positive"]
            breadth_fail = not row["stress_asset_breadth_pass"]
            if agg_fail and breadth_fail:
                reason = "FAILED_2023_HOLDOUT_MULTIPLE_GATES"
            elif agg_fail:
                reason = "FAILED_2023_HOLDOUT_AGGREGATE_STRESS_GATE"
            else:
                reason = "FAILED_2023_HOLDOUT_STRESS_ASSET_BREADTH_GATE"
        else:
            proposed = "BLOCKED"
            reason = "BLOCKED_BY_FOCUSED_HOLDOUT_INTEGRITY"
        decisions.append(
            {
                "candidate_id": row["candidate_id"],
                "variant_id": row["variant_id"],
                "current_state": states[row["variant_id"]],
                "mechanical_gate_result": row["mechanical_holdout_gate_pass"],
                "proposed_state": proposed,
                "reason_code": reason,
                "evidence_artifact": str(MD_PATH),
            }
        )
    return decisions


def build_review(root: Path = Path(".")) -> dict[str, Any]:
    root = root.resolve()
    spec = _load_json(root / SPEC_PATH)
    if spec["preregistration_id"] != "PREREGISTER_FOCUSED_TREND_VALIDATION_V1":
        raise ValueError("unsupported focused trend validation spec")
    planned = expand_planned_holdout_runs(root / SPEC_PATH, repo_root=root)
    if len(planned) != 18:
        raise ValueError("BLOCKED_BY_FOCUSED_HOLDOUT_INTEGRITY")
    by_trial, focused_events = _events_by_trial(root, planned)
    receipts, metrics_paths = _run_artifacts(root)
    expected_set = {row["trial_id"] for row in planned}
    if set(receipts) != expected_set or set(metrics_paths) != expected_set:
        raise ValueError("BLOCKED_BY_FOCUSED_HOLDOUT_INTEGRITY")

    cells: list[dict[str, Any]] = []
    integrity_failures: dict[str, list[str]] = {row["trial_id"]: [] for row in planned}
    failures_by_variant: dict[str, list[str]] = {row["variant_id"]: [] for row in planned}
    for plan in planned:
        trial_id = plan["trial_id"]
        events = by_trial.get(trial_id, [])
        if len(events) != 1:
            integrity_failures[trial_id].append("canonical_event_count")
            failures_by_variant[plan["variant_id"]].append(trial_id)
            continue
        receipt_path = receipts[trial_id]
        metrics_path = metrics_paths[trial_id]
        receipt = _load_json(receipt_path)
        metrics = _load_json(metrics_path)
        receipt_valid, failures = _validate_receipt(
            root=root,
            plan=plan,
            event=events[0],
            receipt_path=receipt_path,
            metrics_path=metrics_path,
            receipt=receipt,
            metrics=metrics,
            spec=spec,
        )
        for key in COMPACT_METRIC_KEYS:
            _finite_number(metrics[key], f"{metrics_path}:{key}")
        if failures:
            integrity_failures[trial_id].extend(failures)
            failures_by_variant[plan["variant_id"]].append(trial_id)
        primary_value = _finite_number(metrics[PRIMARY_METRIC], f"{metrics_path}:{PRIMARY_METRIC}")
        cells.append(
            {
                "trial_id": trial_id,
                "candidate_id": plan["candidate_id"],
                "variant_id": plan["variant_id"],
                "family": receipt["family_id"],
                "parameters_json": receipt["parameters"],
                "symbol": plan["asset"],
                "period_id": plan["period"],
                "cost_mode": plan["cost_mode"],
                "fee_bps": float(events[0]["fee_bps"]),
                "slippage_bps": float(events[0]["slippage_bps"]),
                "input_sha256": events[0]["input_sha256"],
                "receipt_sha256": sha256_path(receipt_path),
                "observation_count": int(metrics["observation_count"]),
                "trade_count": int(metrics["trade_count"]),
                "exposure_fraction": float(metrics["exposure_fraction"]),
                "gross_return": float(metrics["gross_return"]),
                "net_return": float(metrics["net_return"]),
                "buy_and_hold_return": float(metrics["buy_and_hold_return"]),
                "excess_return_vs_buy_and_hold": float(metrics["excess_return_vs_buy_and_hold"]),
                "total_cost": float(metrics["total_cost"]),
                "maximum_drawdown": float(metrics["maximum_drawdown"]),
                "primary_metric_name": PRIMARY_METRIC,
                "primary_metric_value": primary_value,
                "primary_positive": primary_value > 0,
                "receipt_valid": receipt_valid,
                "normalization_provenance_valid": not any(item.startswith("normalization_provenance:") for item in failures),
            }
        )
    if len(cells) != 18:
        raise ValueError("BLOCKED_BY_FOCUSED_HOLDOUT_INTEGRITY")
    variants = _variant_rows(spec, cells, failures_by_variant)
    integrity = _integrity_overview(
        planned=planned,
        focused_events=focused_events,
        by_trial=by_trial,
        receipts=receipts,
        metrics=metrics_paths,
        integrity_failures=integrity_failures,
    )
    hard_fail = integrity["missing"] or integrity["duplicates"] or integrity["unexpected"] or integrity["failed"]
    if hard_fail:
        raise ValueError("BLOCKED_BY_FOCUSED_HOLDOUT_INTEGRITY " + _json_dumps(integrity))
    states = _state_by_variant(root)
    proposed = _proposed_decisions(variants, states)
    return {
        "review_id": "REVIEW_FOCUSED_TREND_2023_HOLDOUT_V1",
        "primary_metric": PRIMARY_METRIC,
        "aggregation_method": "sum_primary_by_exact_variant_and_cost_mode",
        "strict_positivity": "> 0",
        "spec_path": str(SPEC_PATH),
        "runs_dir": str(RUNS_DIR),
        "cells": cells,
        "variants": variants,
        "trial_integrity": integrity,
        "proposed_decisions": proposed,
        "family_status": {
            "time_series_momentum": "one exact variant tested in the holdout",
            "moving_average_trend": "two exact variants tested in the holdout",
        },
        "explicit_non_actions": [
            "NOT TESTED: distinctness diagnostics",
            "NOT TESTED: forward validation",
            "NOT TESTED: portfolio construction",
            "NOT TESTED: additional backtests",
            "NOT TESTED: family-wide decision",
        ],
    }


def write_outputs(review: dict[str, Any], root: Path = Path(".")) -> dict[str, str]:
    root = root.resolve()
    (root / SUMMARY_DIR).mkdir(parents=True, exist_ok=True)
    _write_csv(root / CELLS_PATH, CELL_FIELDS, review["cells"])
    _write_csv(root / VARIANTS_PATH, VARIANT_FIELDS, review["variants"])
    (root / JSON_PATH).write_bytes(canonical_bytes(review) + b"\n")
    (root / MD_PATH).write_text(_markdown(review), encoding="utf-8")
    return {
        str(CELLS_PATH): sha256_path(root / CELLS_PATH),
        str(VARIANTS_PATH): sha256_path(root / VARIANTS_PATH),
        str(JSON_PATH): sha256_path(root / JSON_PATH),
        str(MD_PATH): sha256_path(root / MD_PATH),
    }


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format(row[field]) for field in fields})


def _metric_line(row: dict[str, Any], mode: str) -> str:
    values = row[f"{mode}_primary_by_asset"]
    return ", ".join(f"{asset}={values[asset]:.12g}" for asset in ("BTCUSDT", "ETHUSDT", "SOLUSDT"))


def _markdown(review: dict[str, Any]) -> str:
    lines = [
        "# Scope",
        "MECHANICAL FACT: This review covers exactly three registered FOLLOW_UP variants and 18 focused 2023 holdout cells.",
        "# Holdout Contract",
        "MECHANICAL FACT: 3 variants x 3 assets x 2 cost modes; 2023-01-01T00:00:00Z through 2023-12-31T23:00:00Z.",
        "# Trial Integrity",
        "MECHANICAL FACT: " + _json_dumps(review["trial_integrity"]),
        "# Primary Metric Contract",
        "MECHANICAL FACT: primary metric is excess_return_vs_buy_and_hold; aggregation is the preregistered variant-level sum by cost mode; positivity is strict > 0.",
        "# Cell-Level Results",
        f"MECHANICAL FACT: Cell CSV contains {len(review['cells'])} deterministic rows at {CELLS_PATH}.",
        "# Variant-Level Results",
    ]
    for row in review["variants"]:
        lines.append(
            "MECHANICAL FACT: "
            f"{row['candidate_id']} baseline [{_metric_line(row, 'baseline')}], "
            f"stress [{_metric_line(row, 'stress')}], "
            f"stress aggregate={row['stress_primary_aggregate']:.12g}, "
            f"stress positive assets={row['stress_positive_asset_count']}, "
            f"gate={row['mechanical_holdout_gate_pass']}."
        )
    lines.extend(
        [
            "# Frozen Gate Evaluation",
            "MECHANICAL FACT: The frozen gate requires completion, zero integrity failures, stress aggregate > 0, and at least two stress-positive assets.",
            "# Baseline Versus Stress",
            "MECHANICAL FACT: Baseline results are reported as context only and do not override stress gate failures.",
            "# Asset Breadth",
            "MECHANICAL FACT: Stress asset breadth uses strict primary metric positivity per asset and requires at least two of three assets.",
            "# Trade and Cost Context",
            "MECHANICAL FACT: Trade counts and total costs are summarized mechanically in the variant CSV.",
            "# Drawdown Context",
            "MECHANICAL FACT: Worst maximum drawdown by cost mode is reported mechanically and is not a continuation gate.",
            "# Mechanical Findings",
        ]
    )
    for row in review["variants"]:
        reasons = ",".join(row["failure_reasons"]) or "NONE"
        lines.append(f"MECHANICAL FACT: {row['candidate_id']} failure_reasons={reasons}.")
    lines.extend(
        [
            "# Research Judgment Boundary",
            "RESEARCH JUDGMENT: This review does not claim validation, robustness, production readiness, profitability, independence, or diversification.",
            "# Proposed Exact-Variant Decisions",
        ]
    )
    for row in review["proposed_decisions"]:
        lines.append("MECHANICAL FACT: " + _json_dumps(row))
    lines.extend(
        [
            "# Family-Level Status",
            "MECHANICAL FACT: time_series_momentum has one exact variant tested in the holdout.",
            "MECHANICAL FACT: moving_average_trend has two exact variants tested in the holdout.",
            "RESEARCH JUDGMENT: No family-wide decision is made.",
            "# Explicit Non-Actions",
        ]
    )
    lines.extend(review["explicit_non_actions"])
    lines.extend(
        [
            "# Reproduction",
            "MECHANICAL FACT: Run `python -m qntylab.focused_trend_holdout_review` from the repository root.",
            "",
        ]
    )
    return "\n".join(lines)


def artifact_hashes(root: Path = Path(".")) -> dict[str, str]:
    root = root.resolve()
    return {str(path): sha256_path(root / path) for path in (CELLS_PATH, VARIANTS_PATH, JSON_PATH, MD_PATH)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Review focused trend 2023 holdout without executing strategies.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    review = build_review(args.root)
    hashes = write_outputs(review, args.root)
    print(json.dumps({"artifact_sha256": hashes, "proposed_decisions": review["proposed_decisions"]}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
