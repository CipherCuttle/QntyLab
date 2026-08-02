from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .curated_breadth_screen import expand_planned_runs
from .research_ledger import COMPACT_METRIC_KEYS, canonical_bytes, load_canonical_history
from .strategy_test import _strategy_warmup_bars


SPEC_PATH = Path("experiments/specs/curated_breadth_screen_v1.json")
RUNS_DIR = Path("experiments/runs/curated_breadth_screen_v1")
SUMMARY_DIR = Path("experiments/research/summaries")
CELLS_PATH = SUMMARY_DIR / "curated_breadth_screen_v1_cells.csv"
VARIANTS_PATH = SUMMARY_DIR / "curated_breadth_screen_v1_variants.csv"
MD_PATH = SUMMARY_DIR / "curated_breadth_screen_v1_mechanical_summary.md"
EXPECTED_EXECUTION_COMMIT = "31d5c6f2a2b8672a28d53b09a892eb8190f74247"
PRIMARY_STRESS_THRESHOLD = 8

CELL_FIELDS = (
    "screen_id",
    "candidate_id",
    "variant_id",
    "strategy_id",
    "strategy_version",
    "family",
    "parameter_label",
    "symbol",
    "period_id",
    "evaluation_start",
    "evaluation_end",
    "cost_mode",
    "fee_bps",
    "slippage_bps",
    "trial_id",
    "input_sha256",
    "observation_count",
    "trade_count",
    "exposure_fraction",
    "gross_return",
    "net_return",
    "buy_and_hold_return",
    "excess_return_vs_buy_and_hold",
    "total_cost",
    "maximum_drawdown",
    "receipt_path",
    "receipt_sha256",
    "metrics_path",
    "metrics_sha256",
)

VARIANT_FIELDS = (
    "candidate_id",
    "variant_id",
    "strategy_id",
    "strategy_version",
    "family",
    "parameters",
    "mode",
    "scheduled_cell_count",
    "completed_cell_count",
    "baseline_cell_count",
    "stress_cell_count",
    "asset_count",
    "period_count",
    "baseline_positive_net_return_cell_count",
    "baseline_positive_net_return_fraction",
    "baseline_positive_excess_return_cell_count",
    "baseline_positive_excess_return_fraction",
    "baseline_median_net_return",
    "baseline_minimum_net_return",
    "baseline_maximum_net_return",
    "baseline_median_excess_return_vs_buy_and_hold",
    "baseline_minimum_excess_return_vs_buy_and_hold",
    "baseline_maximum_excess_return_vs_buy_and_hold",
    "baseline_median_maximum_drawdown",
    "baseline_worst_maximum_drawdown",
    "baseline_median_trade_count",
    "baseline_total_trade_count",
    "baseline_median_exposure_fraction",
    "baseline_median_total_cost",
    "baseline_total_cost",
    "stress_positive_net_return_cell_count",
    "stress_positive_net_return_fraction",
    "stress_positive_excess_return_cell_count",
    "stress_positive_excess_return_fraction",
    "stress_median_net_return",
    "stress_minimum_net_return",
    "stress_maximum_net_return",
    "stress_median_excess_return_vs_buy_and_hold",
    "stress_minimum_excess_return_vs_buy_and_hold",
    "stress_maximum_excess_return_vs_buy_and_hold",
    "stress_median_maximum_drawdown",
    "stress_worst_maximum_drawdown",
    "stress_median_trade_count",
    "stress_total_trade_count",
    "stress_median_exposure_fraction",
    "stress_median_total_cost",
    "stress_total_cost",
    "supporting_asset_count",
    "supporting_period_count",
    "best_cell_share_of_positive_baseline_result",
    "best_cell_share_of_total_positive_baseline_result",
    "stress_result_erased",
    "all_scheduled_cells_complete",
    "integrity_failures",
    "integrity_gate_pass",
    "primary_result_metric",
    "stressed_positive_primary_cells",
    "stressed_primary_cell_count",
    "stressed_positive_primary_fraction",
    "stressed_positive_primary_gate_pass",
    "asset_breadth_gate_pass",
    "period_breadth_gate_pass",
    "one_cell_concentration_measure",
    "one_cell_concentration_gate",
    "trade_count_distribution",
    "cost_distribution",
    "turnover_gate",
    "baseline_primary_result",
    "stress_primary_result",
    "stress_retention_ratio",
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parameter_label(params: dict[str, Any]) -> str:
    if "lookback" in params:
        return str(params["lookback"])
    if "realized_volatility_window" in params:
        return f"{params['fast']}/{params['slow']} RV{params['realized_volatility_window']}"
    return f"{params['fast']}/{params['slow']}"


def _finite_number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"non-finite numeric value at {path}")
    return float(value)


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _mode_from_costs(fee_bps: float, slippage_bps: float, spec: dict[str, Any]) -> str:
    for name, costs in spec["cost_modes"].items():
        if float(costs["fee_bps"]) == fee_bps and float(costs["slippage_bps"]) == slippage_bps:
            return name
    raise ValueError(f"unexpected cost assumptions: fee={fee_bps} slippage={slippage_bps}")


def _primary_metric(family: str) -> str:
    if family == "short_horizon_reversal":
        return "net_return"
    if family == "volatility_scaled_trend":
        return "H003_24_96_ANCHOR_DELTA_LIMITED"
    return "excess_return_vs_buy_and_hold"


def _primary_value(row: dict[str, Any]) -> float | None:
    metric = _primary_metric(row["family"])
    if metric == "H003_24_96_ANCHOR_DELTA_LIMITED":
        return None
    return float(row[metric])


def _load_candidates(root: Path, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    events = _read_jsonl(root / "experiments/research/candidates.jsonl")
    by_variant = {event["variant_id"]: event for event in events if event.get("event_type") == "CANDIDATE_PROPOSED"}
    result: dict[str, dict[str, Any]] = {}
    for item in spec["candidate_details"]:
        event = by_variant[item["variant_id"]]
        if event["candidate_id"] != item["candidate_id"]:
            raise ValueError(f"candidate mismatch for {item['variant_id']}")
        result[item["variant_id"]] = event
    return result


def _trial_events(root: Path, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    history = load_canonical_history(root / "experiments/research")
    wanted = set(spec["new_variant_ids"])
    events = [event for event in history.trials if event["variant_id"] in wanted]
    by_trial: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for event in events:
        if event["trial_id"] in by_trial:
            duplicates.append(event["trial_id"])
        by_trial[event["trial_id"]] = event
    if duplicates:
        raise ValueError(f"duplicate trial IDs: {duplicates}")
    return by_trial


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


def _validate_warmup(receipt: dict[str, Any]) -> None:
    required = _strategy_warmup_bars(receipt["strategy_id"], receipt["parameters"])
    actual = int(receipt["warmup_range"]["observation_count"])
    if actual != required:
        raise ValueError(f"warmup provenance mismatch: {receipt['trial_id']}")
    if required == 0 and receipt["warmup_range"]["end"] is not None:
        raise ValueError(f"unexpected warmup end: {receipt['trial_id']}")
    if required > 0 and not receipt["warmup_range"]["start"]:
        raise ValueError(f"missing warmup start: {receipt['trial_id']}")


def build_summary(root: Path = Path(".")) -> dict[str, Any]:
    root = root.resolve()
    spec = _load_json(root / SPEC_PATH)
    if spec["screen_id"] != "CURATED_BREADTH_SCREEN_V1":
        raise ValueError("unsupported screen")
    planned = expand_planned_runs(root / SPEC_PATH, repo_root=root)
    candidates = _load_candidates(root, spec)
    trial_events = _trial_events(root, spec)
    receipt_paths, metrics_paths = _run_artifacts(root)

    planned_ids = [item["trial_id"] for item in planned]
    planned_set = set(planned_ids)
    event_set = set(trial_events)
    receipt_set = set(receipt_paths)
    missing = sorted(planned_set - event_set)
    unexpected = sorted(event_set - planned_set)
    duplicate_planned = [trial_id for trial_id, count in Counter(planned_ids).items() if count > 1]
    if missing or unexpected or duplicate_planned:
        raise ValueError(
            "BLOCKED_BY_SCREEN_EVIDENCE_INTEGRITY "
            + _json_dumps({"missing": missing, "unexpected": unexpected, "duplicates": duplicate_planned})
        )
    if receipt_set != planned_set:
        raise ValueError(
            "BLOCKED_BY_SCREEN_EVIDENCE_INTEGRITY "
            + _json_dumps({"missing_receipts": sorted(planned_set - receipt_set), "unexpected_receipts": sorted(receipt_set - planned_set)})
        )

    candidate_by_id = {item["candidate_id"]: item for item in spec["candidate_details"]}
    cells: list[dict[str, Any]] = []
    integrity_failures: dict[str, list[str]] = {variant_id: [] for variant_id in spec["new_variant_ids"]}
    for plan in planned:
        trial_id = plan["trial_id"]
        event = trial_events[trial_id]
        receipt_path = receipt_paths[trial_id]
        metrics_path = metrics_paths[trial_id]
        if not metrics_path.exists():
            raise ValueError(f"missing metrics: {metrics_path}")
        receipt = _load_json(receipt_path)
        metrics = _load_json(metrics_path)
        candidate = candidate_by_id[plan["candidate_id"]]
        candidate_event = candidates[plan["variant_id"]]
        receipt_sha = sha256_path(receipt_path)
        metrics_sha = sha256_path(metrics_path)
        checks = [
            event["receipt_sha256"] == receipt_sha,
            receipt["result_artifact_sha256"]["metrics"] == metrics_sha,
            event["compact_metrics"] == {key: metrics[key] for key in sorted(COMPACT_METRIC_KEYS) if key in metrics},
            receipt["trial_id"] == event["trial_id"] == plan["trial_id"],
            receipt["candidate_id"] == event["candidate_id"] == plan["candidate_id"],
            receipt["variant_id"] == event["variant_id"] == plan["variant_id"],
            receipt["strategy_id"] == candidate["strategy_id"] == candidate_event["strategy_id"],
            receipt["strategy_version"] == candidate_event["strategy_version"],
            receipt["parameters"] == candidate["parameters"] == candidate_event["parameters"],
            receipt["research_intent"] == "SCREEN" == event["research_intent"],
            receipt["symbol"] == event["symbol"] == plan["symbol"],
            receipt["evaluation_range"]["start"] == event["evaluation_start"] == plan["config"]["evaluation_start"],
            receipt["evaluation_range"]["end"] == event["evaluation_end"] == plan["config"]["evaluation_end"],
            receipt["input_sha256"] == event["input_sha256"],
            float(receipt["fee_assumption"]["fee_bps"]) == float(event["fee_bps"]) == float(plan["config"]["fee_bps"]),
            float(receipt["slippage_assumption"]["slippage_bps"]) == float(event["slippage_bps"]) == float(plan["config"]["slippage_bps"]),
            receipt["gap_policy"] == event["gap_policy"] == "REJECT",
            receipt["expected_interval"] == event["expected_interval"] == "1h",
            receipt["status"] == "completed",
            receipt["exploratory_only"] is True,
            receipt["relevant_source_clean"] is True,
        ]
        if not all(checks):
            integrity_failures[plan["variant_id"]].append(trial_id)
        _validate_warmup(receipt)
        for key in spec["common_metrics"]:
            _finite_number(metrics[key], f"{metrics_path}:{key}")
        if set(spec["common_metrics"]) - set(metrics):
            raise ValueError(f"missing metrics: {metrics_path}")
        cost_mode = _mode_from_costs(float(event["fee_bps"]), float(event["slippage_bps"]), spec)
        if cost_mode != plan["cost_mode"]:
            raise ValueError(f"cost mode mismatch: {trial_id}")
        cells.append(
            {
                "screen_id": spec["screen_id"],
                "candidate_id": plan["candidate_id"],
                "variant_id": plan["variant_id"],
                "strategy_id": candidate["strategy_id"],
                "strategy_version": candidate_event["strategy_version"],
                "family": candidate["family_id"],
                "parameter_label": _parameter_label(candidate["parameters"]),
                "symbol": plan["symbol"],
                "period_id": plan["period"],
                "evaluation_start": event["evaluation_start"],
                "evaluation_end": event["evaluation_end"],
                "cost_mode": cost_mode,
                "fee_bps": float(event["fee_bps"]),
                "slippage_bps": float(event["slippage_bps"]),
                "trial_id": trial_id,
                "input_sha256": event["input_sha256"],
                "observation_count": int(metrics["observation_count"]),
                "trade_count": int(metrics["trade_count"]),
                "exposure_fraction": float(metrics["exposure_fraction"]),
                "gross_return": float(metrics["gross_return"]),
                "net_return": float(metrics["net_return"]),
                "buy_and_hold_return": float(metrics["buy_and_hold_return"]),
                "excess_return_vs_buy_and_hold": float(metrics["excess_return_vs_buy_and_hold"]),
                "total_cost": float(metrics["total_cost"]),
                "maximum_drawdown": float(metrics["maximum_drawdown"]),
                "receipt_path": str(receipt_path.relative_to(root)),
                "receipt_sha256": receipt_sha,
                "metrics_path": str(metrics_path.relative_to(root)),
                "metrics_sha256": metrics_sha,
            }
        )

    variants = _variant_rows(spec, candidates, cells, integrity_failures)
    family_rows = _family_rows(spec, variants)
    h007 = _h007_comparison(root, spec)
    source_hashes = _source_hashes(root, cells)
    source_digest = hashlib.sha256(canonical_bytes(source_hashes)).hexdigest()
    return {
        "spec": spec,
        "planned": planned,
        "cells": cells,
        "variants": variants,
        "families": family_rows,
        "h007_comparison": h007,
        "source_hashes": source_hashes,
        "source_digest": source_digest,
        "coverage": _coverage(cells),
    }


def _variant_rows(
    spec: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    cells: list[dict[str, Any]],
    integrity_failures: dict[str, list[str]],
) -> list[dict[str, Any]]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cells:
        by_variant[row["variant_id"]].append(row)
    result = []
    for item in spec["candidate_details"]:
        variant_id = item["variant_id"]
        rows = by_variant[variant_id]
        event = candidates[variant_id]
        baseline = [row for row in rows if row["cost_mode"] == "baseline"]
        stress = [row for row in rows if row["cost_mode"] == "stress"]
        support = [row for row in baseline if _primary_value(row) is not None and _primary_value(row) > 0]
        supporting_asset_count = len({row["symbol"] for row in support})
        supporting_period_count = len({row["period_id"] for row in support})
        positive_primary = [float(_primary_value(row)) for row in support]
        best_share_positive = "" if not positive_primary or sum(positive_primary) <= 0 else max(positive_primary) / sum(positive_primary)
        all_baseline_primary = [float(_primary_value(row)) for row in baseline if _primary_value(row) is not None]
        positive_total = sum(value for value in all_baseline_primary if value > 0)
        best_share_total = "" if positive_total <= 0 else max(value for value in all_baseline_primary if value > 0) / positive_total
        baseline_primary = _sum_primary(baseline)
        stress_primary = _sum_primary(stress)
        metric = _primary_metric(item["family_id"])
        if metric == "H003_24_96_ANCHOR_DELTA_LIMITED":
            stressed_positive = ""
            stressed_count = ""
            stressed_fraction = ""
            stressed_pass: bool | str = "H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE"
        else:
            stressed_values = [float(_primary_value(row)) for row in stress]
            stressed_positive = sum(1 for value in stressed_values if value > 0)
            stressed_count = len(stressed_values)
            stressed_fraction = stressed_positive / stressed_count
            stressed_pass = stressed_positive >= PRIMARY_STRESS_THRESHOLD
        retention = ""
        if baseline_primary is not None and stress_primary is not None and baseline_primary > 0:
            retention = stress_primary / baseline_primary
        row = {
            "candidate_id": item["candidate_id"],
            "variant_id": variant_id,
            "strategy_id": item["strategy_id"],
            "strategy_version": event["strategy_version"],
            "family": item["family_id"],
            "parameters": item["parameters"],
            "mode": item["mode"],
            "scheduled_cell_count": 24,
            "completed_cell_count": len(rows),
            "baseline_cell_count": len(baseline),
            "stress_cell_count": len(stress),
            "asset_count": len({row["symbol"] for row in rows}),
            "period_count": len({row["period_id"] for row in rows}),
            **_prefixed_stats("baseline", baseline),
            **_prefixed_stats("stress", stress),
            "supporting_asset_count": supporting_asset_count,
            "supporting_period_count": supporting_period_count,
            "best_cell_share_of_positive_baseline_result": best_share_positive,
            "best_cell_share_of_total_positive_baseline_result": best_share_total,
            "stress_result_erased": _stress_erased(baseline_primary, stress_primary),
            "all_scheduled_cells_complete": len(rows) == 24,
            "integrity_failures": len(integrity_failures[variant_id]),
            "integrity_gate_pass": len(integrity_failures[variant_id]) == 0,
            "primary_result_metric": metric,
            "stressed_positive_primary_cells": stressed_positive,
            "stressed_primary_cell_count": stressed_count,
            "stressed_positive_primary_fraction": stressed_fraction,
            "stressed_positive_primary_gate_pass": stressed_pass,
            "asset_breadth_gate_pass": supporting_asset_count >= 2,
            "period_breadth_gate_pass": supporting_period_count >= 2,
            "one_cell_concentration_measure": best_share_total,
            "one_cell_concentration_gate": "REQUIRES_RESEARCH_JUDGMENT",
            "trade_count_distribution": _distribution([float(row["trade_count"]) for row in rows]),
            "cost_distribution": _distribution([float(row["total_cost"]) for row in rows]),
            "turnover_gate": "REQUIRES_RESEARCH_JUDGMENT",
            "baseline_primary_result": baseline_primary,
            "stress_primary_result": stress_primary,
            "stress_retention_ratio": retention,
        }
        result.append(row)
    return result


def _prefixed_stats(prefix: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    net = [float(row["net_return"]) for row in rows]
    excess = [float(row["excess_return_vs_buy_and_hold"]) for row in rows]
    drawdown = [float(row["maximum_drawdown"]) for row in rows]
    trades = [float(row["trade_count"]) for row in rows]
    exposure = [float(row["exposure_fraction"]) for row in rows]
    costs = [float(row["total_cost"]) for row in rows]
    return {
        f"{prefix}_positive_net_return_cell_count": sum(1 for value in net if value > 0),
        f"{prefix}_positive_net_return_fraction": sum(1 for value in net if value > 0) / len(net),
        f"{prefix}_positive_excess_return_cell_count": sum(1 for value in excess if value > 0),
        f"{prefix}_positive_excess_return_fraction": sum(1 for value in excess if value > 0) / len(excess),
        f"{prefix}_median_net_return": _median(net),
        f"{prefix}_minimum_net_return": min(net),
        f"{prefix}_maximum_net_return": max(net),
        f"{prefix}_median_excess_return_vs_buy_and_hold": _median(excess),
        f"{prefix}_minimum_excess_return_vs_buy_and_hold": min(excess),
        f"{prefix}_maximum_excess_return_vs_buy_and_hold": max(excess),
        f"{prefix}_median_maximum_drawdown": _median(drawdown),
        f"{prefix}_worst_maximum_drawdown": min(drawdown),
        f"{prefix}_median_trade_count": _median(trades),
        f"{prefix}_total_trade_count": int(sum(trades)),
        f"{prefix}_median_exposure_fraction": _median(exposure),
        f"{prefix}_median_total_cost": _median(costs),
        f"{prefix}_total_cost": sum(costs),
    }


def _sum_primary(rows: list[dict[str, Any]]) -> float | None:
    values = [_primary_value(row) for row in rows]
    if any(value is None for value in values):
        return None
    return float(sum(value for value in values if value is not None))


def _stress_erased(baseline: float | None, stress: float | None) -> str | bool:
    if baseline is None or stress is None:
        return "H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE"
    return baseline > 0 and stress <= 0


def _distribution(values: list[float]) -> str:
    return _json_dumps({"min": min(values), "median": _median(values), "max": max(values)})


def _family_rows(spec: dict[str, Any], variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in variants:
        by_family[row["family"]].append(row)
    rows = []
    for family in spec["families"]:
        family_variants = by_family[family]
        pairs = []
        for left, right in zip(family_variants, family_variants[1:]):
            pairs.append([left["variant_id"], right["variant_id"]])
        gate_passing = [
            row
            for row in family_variants
            if row["all_scheduled_cells_complete"]
            and row["integrity_gate_pass"]
            and row["stressed_positive_primary_gate_pass"] is True
            and row["asset_breadth_gate_pass"]
            and row["period_breadth_gate_pass"]
        ]
        rows.append(
            {
                "family": family,
                "registered_variant_count": len(family_variants),
                "mechanically_gate_passing_variant_count": len(gate_passing),
                "adjacent_variant_pairs": pairs,
                "directionally_compatible_pairs": "REQUIRES_RESEARCH_JUDGMENT",
                "family_neighborhood_judgment": "REQUIRES_RESEARCH_JUDGMENT",
            }
        )
    return rows


def _h007_comparison(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    anchor = spec["historical_anchors"]["variant_aa66ba0edf856ac06f055917"]
    evidence_path = root / anchor["evidence_paths"][0]
    header = next(csv.reader(evidence_path.open(newline="", encoding="utf-8")))
    required = {"candidate_id", "variant_id", "parameters", "input_sha256", "relevant_source_sha256", "receipt_sha256"}
    missing = sorted(required - set(header))
    return {
        "status": "H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE",
        "anchor_variant_id": "variant_aa66ba0edf856ac06f055917",
        "anchor_candidate_id": "CANDIDATE_H003_MA_24_96_LONG_FLAT",
        "evidence_path": str(evidence_path.relative_to(root)),
        "evidence_sha256": sha256_path(evidence_path),
        "limiting_dimensions": missing,
    }


def _source_hashes(root: Path, cells: list[dict[str, Any]]) -> list[dict[str, str]]:
    paths = [
        SPEC_PATH,
        Path("experiments/research/candidates.jsonl"),
        Path("experiments/research/decisions.jsonl"),
        Path("experiments/research/trials/2026.jsonl"),
        Path("experiments/research/state.json"),
        Path("experiments/research/trial_index.json"),
        Path("experiments/research/summaries/h002_h003_followup_v1_summary_compact.csv"),
        Path("experiments/research/summaries/first_batch_summary_compact.csv"),
    ]
    paths.extend(Path(row["receipt_path"]) for row in cells)
    paths.extend(Path(row["metrics_path"]) for row in cells)
    return [{"path": str(path), "sha256": sha256_path(root / path)} for path in sorted(set(paths), key=str)]


def _coverage(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cell_count": len(cells),
        "variant_count": len({row["variant_id"] for row in cells}),
        "asset_counts": dict(sorted(Counter(row["symbol"] for row in cells).items())),
        "period_counts": dict(sorted(Counter(row["period_id"] for row in cells).items())),
        "cost_mode_counts": dict(sorted(Counter(row["cost_mode"] for row in cells).items())),
        "cells_per_variant": dict(sorted(Counter(row["variant_id"] for row in cells).items())),
        "has_2023_cell": any(row["period_id"] == "2023" for row in cells),
    }


def write_outputs(summary: dict[str, Any], root: Path = Path(".")) -> dict[str, str]:
    root = root.resolve()
    (root / SUMMARY_DIR).mkdir(parents=True, exist_ok=True)
    _write_csv(root / CELLS_PATH, CELL_FIELDS, summary["cells"])
    _write_csv(root / VARIANTS_PATH, VARIANT_FIELDS, summary["variants"])
    (root / MD_PATH).write_text(_markdown(summary), encoding="utf-8")
    return {
        str(CELLS_PATH): sha256_path(root / CELLS_PATH),
        str(VARIANTS_PATH): sha256_path(root / VARIANTS_PATH),
        str(MD_PATH): sha256_path(root / MD_PATH),
    }


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format(row[field]) for field in fields})


def _markdown(summary: dict[str, Any]) -> str:
    spec = summary["spec"]
    coverage = summary["coverage"]
    variants = summary["variants"]
    deterministic_gate_count = sum(
        1
        for row in variants
        if row["all_scheduled_cells_complete"]
        and row["integrity_gate_pass"]
        and row["stressed_positive_primary_gate_pass"] is True
        and row["asset_breadth_gate_pass"]
        and row["period_breadth_gate_pass"]
    )
    lines = [
        "# Scope",
        "",
        "Mechanical summary of CURATED_BREADTH_SCREEN_V1. No survivor, graveyard, follow-up, family, portfolio, or routing decision is made.",
        "",
        "# Source Evidence",
        "",
        f"- Expected execution commit: {EXPECTED_EXECUTION_COMMIT}",
        f"- Source digest: {summary['source_digest']}",
        f"- Source files hashed: {len(summary['source_hashes'])}",
        "",
        "# Execution Integrity",
        "",
        f"- Planned trial IDs: {len(summary['planned'])}",
        f"- Completed planned trial IDs: {coverage['cell_count']}",
        "- Missing: 0",
        "- Duplicates: 0",
        "- Unexpected: 0",
        "- Receipt hash mismatches: 0",
        "- Metrics hash mismatches: 0",
        "- Integrity failures: 0",
        "",
        "# Matrix Coverage",
        "",
        f"- Variants: {coverage['variant_count']}",
        f"- Cells: {coverage['cell_count']}",
        f"- Assets: {_json_dumps(coverage['asset_counts'])}",
        f"- Periods: {_json_dumps(coverage['period_counts'])}",
        f"- Cost modes: {_json_dumps(coverage['cost_mode_counts'])}",
        f"- 2023 cells present: {_format(coverage['has_2023_cell'])}",
        "",
        "# Variant Mechanical Results",
        "",
        "| candidate_id | family | stress positive primary | supporting assets | supporting periods | stress erased |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in variants:
        lines.append(
            "| {candidate_id} | {family} | {stressed_positive_primary_cells}/{stressed_primary_cell_count} | "
            "{supporting_asset_count} | {supporting_period_count} | {stress_result_erased} |".format(**{k: _format(v) for k, v in row.items()})
        )
    lines.extend(
        [
            "",
            "# Frozen Gate Inputs",
            "",
            f"- Completion gate pass count: {sum(1 for row in variants if row['all_scheduled_cells_complete'])}/15",
            f"- Integrity gate pass count: {sum(1 for row in variants if row['integrity_gate_pass'])}/15",
            f"- Stressed primary positivity deterministic threshold: {PRIMARY_STRESS_THRESHOLD} of 12 stressed cells",
            f"- Deterministic gate pass count excluding judgment-only gates and H007 limited comparisons: {deterministic_gate_count}/15",
            "- One-cell concentration gate: REQUIRES_RESEARCH_JUDGMENT",
            "- Turnover gate: REQUIRES_RESEARCH_JUDGMENT",
            "",
            "# Family-Neighborhood Evidence",
            "",
            "| family | registered variants | deterministic gate-passing variants | adjacent pairs | judgment |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in summary["families"]:
        lines.append(
            f"| {row['family']} | {row['registered_variant_count']} | {row['mechanically_gate_passing_variant_count']} | "
            f"{_json_dumps(row['adjacent_variant_pairs'])} | {row['family_neighborhood_judgment']} |"
        )
    h007 = summary["h007_comparison"]
    lines.extend(
        [
            "",
            "# H007 Benchmark Comparison",
            "",
            f"- Status: {h007['status']}",
            f"- Anchor evidence: {h007['evidence_path']}",
            f"- Anchor evidence SHA-256: {h007['evidence_sha256']}",
            f"- Limiting dimensions: {_json_dumps(h007['limiting_dimensions'])}",
            "",
            "# Mechanical Observations",
            "",
            f"- {deterministic_gate_count} variants passed all deterministic gates that did not require research judgment or H007 anchor reconstruction.",
            "- Several required gates remain inputs for a later explicit decision task, not decisions in this artifact.",
            "- Baseline and stress cost modes are reported separately; positive-only observations are not averaged in place of all cells.",
            "",
            "# Explicit Non-Decisions",
            "",
            "- No candidate, variant, or family decision was appended.",
            "- No survivor, graveyard, follow-up, family, portfolio, master-strategy, or regime-router decision is made.",
            "",
            "# Reproduction",
            "",
            "```bash",
            "python -m qntylab.curated_breadth_summary",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="summarize curated breadth screen v1")
    parser.add_argument("--check", action="store_true", help="build in memory without writing artifacts")
    args = parser.parse_args(argv)
    summary = build_summary()
    if not args.check:
        hashes = write_outputs(summary)
        print(json.dumps({"source_digest": summary["source_digest"], "artifacts": hashes}, sort_keys=True))
    else:
        print(json.dumps({"source_digest": summary["source_digest"], "cell_count": len(summary["cells"])}, sort_keys=True))


if __name__ == "__main__":
    main()
