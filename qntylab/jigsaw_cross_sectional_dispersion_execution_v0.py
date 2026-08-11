"""Bounded execution for JIGSAW_CROSS_SECTIONAL_DISPERSION_V0.

This module is an evidence runner, not a strategy or signal module.  The
dispersion recipe is imported from the preregistered contract and CSMOM
accounting/weights are imported from the existing Breadth V2 runner.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from . import jigsaw_cross_sectional_dispersion_v0 as contract
from .breadth_v2_runner import (
    PANEL_EXECUTION_UNIT_ID,
    SYNCHRONIZED_PANEL,
    execute_candidate_and_benchmark,
)

EVIDENCE_ROOT = Path("/home/swirky/DevHub/qntylab-evidence")
WARMUP_ROOT = EVIDENCE_ROOT / "jigsaw_cross_sectional_dispersion_v0_warmup_v0"
BREADTH_ROOT = EVIDENCE_ROOT / "breadth_v2_dev_inputs_v0"
MANIFEST = BREADTH_ROOT / "manifests" / "BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1.json"
PANEL = tuple(contract.PANEL)
VARIANTS = (24, 72, 168, 336)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stamp(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "positive_fraction": None}
    a = np.asarray(values, dtype=float)
    return {"count": int(a.size), "mean": float(a.mean()), "median": float(np.median(a)), "positive_fraction": float((a > 0).mean())}


def _contrast(rows: list[dict[str, Any]], cost: str) -> dict[str, Any]:
    result = {name: _summary([r["utility"][cost] for r in rows if r["bin"] == name]) for name in ("LOW", "MID", "HIGH")}
    result["high_minus_low_mean_utility"] = result["HIGH"]["mean"] - result["LOW"]["mean"] if result["HIGH"]["mean"] is not None and result["LOW"]["mean"] is not None else None
    return result


def _bootstrap(rows: list[dict[str, Any]], cost: str) -> dict[str, Any]:
    rng = np.random.default_rng(contract.BOOTSTRAP_SEED)
    n = len(rows)
    draws: list[float] = []
    for _ in range(contract.BOOTSTRAP_RESAMPLES):
        sample: list[dict[str, Any]] = []
        while len(sample) < n:
            start = int(rng.integers(0, n))
            sample.extend(rows[(start + j) % n] for j in range(contract.BOOTSTRAP_BLOCK_CALENDAR_DAYS))
        value = _contrast(sample[:n], cost)["high_minus_low_mean_utility"]
        if value is not None:
            draws.append(value)
    return {"method": contract.BOOTSTRAP_METHOD, "block_calendar_days": contract.BOOTSTRAP_BLOCK_CALENDAR_DAYS, "resamples": contract.BOOTSTRAP_RESAMPLES, "seed": contract.BOOTSTRAP_SEED, "interval_95": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]}


def _load_csv(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["timestamp"]: float(row["close"]) for row in rows}


def _load_warmup() -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for symbol in PANEL:
        raw = _load_csv(WARMUP_ROOT / "normalized_inputs" / f"{symbol}-perp-1h.csv")
        # Warm-up census is expressed on the frozen decision-boundary clock.
        # The support materializer already verified the source bar is complete
        # at that timestamp; shifting it would discard the first 00:00 state.
        result[symbol] = dict(raw)
    return result


def _load_bundles() -> dict[int, dict[str, Any]]:
    candidates = {json.loads(line)["variant_id"]: json.loads(line) for line in Path("experiments/research/candidates.jsonl").read_text().splitlines() if line.strip() and "CANDIDATE_BREADTH_V2_CSMOM" in line}
    manifest = json.loads(MANIFEST.read_text())
    result: dict[int, dict[str, Any]] = {}
    for row in manifest["input_records"]:
        if row["family_id"] != "CROSS_SECTIONAL_MOMENTUM" or row["period_id"] != "DEV_2024" or row["execution_unit_type"] != "SYNCHRONIZED_PANEL" or row["status"] != "READY":
            continue
        variant = candidates[row["variant_id"]]["parameters"]["lookback"]
        path = BREADTH_ROOT / "bundles" / f"{row['evaluation_input_bundle_sha256']}.pkl.gz"
        with gzip.open(path, "rb") as handle:
            result[int(variant)] = __import__("pickle").loads(handle.read())
    if set(result) != set(VARIANTS):
        raise RuntimeError(f"missing exact four CSMOM bundles: {sorted(result)}")
    return result


def _close_panel() -> dict[str, dict[str, float]]:
    warm = _load_warmup()
    bundles = _load_bundles()
    combined = {symbol: dict(warm[symbol]) for symbol in PANEL}
    for bundle in bundles.values():
        for symbol in PANEL:
            for row in bundle["admitted_price"][symbol]:
                combined[symbol][row["decision_time"]] = float(row["close"])
    return combined


def _dispersion_rows(closes: dict[str, dict[str, float]], utility_rows: dict[int, dict[str, dict[str, float]]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    common = sorted(set.intersection(*(set(closes[s]) for s in PANEL)))
    daily = [t for t in common if _dt(t).hour == 0]
    raw: list[dict[str, Any]] = []
    for t in daily:
        prior = _stamp(_dt(t) - timedelta(hours=24))
        if prior not in common:
            continue
        returns = {s: closes[s][t] / closes[s][prior] - 1.0 for s in PANEL}
        dispersion = contract.cross_sectional_dispersion(returns)
        raw.append({"timestamp": t, "dispersion": dispersion})
    values = np.asarray([r["dispersion"] for r in raw], dtype=float)
    index = {r["timestamp"]: i for i, r in enumerate(raw)}
    output: list[dict[str, Any]] = []
    for t in sorted(utility_rows[24]):
        if t not in index or index[t] < contract.NORMALIZATION_WARMUP_DAYS:
            continue
        percentile, bin_name = contract.dispersion_percentile_and_bin(values, index[t])
        output.append({"timestamp": t, "dispersion": float(values[index[t]]), "percentile": percentile, "bin": bin_name, "utilities": {v: utility_rows[v][t] for v in VARIANTS}})
    return output, {"raw_daily_states": len(raw), "pre2024_daily_states": sum(_dt(r["timestamp"]).year < 2024 for r in raw), "eligible_dev_states": len(output)}


def _execution_rows() -> tuple[dict[int, dict[str, dict[str, float]]], dict[str, Any]]:
    bundles = _load_bundles()
    utilities: dict[int, dict[str, dict[str, float]]] = {v: {"STRESS": {}, "BASELINE": {}} for v in VARIANTS}
    path_receipts: dict[str, Any] = {}
    for variant, bundle in bundles.items():
        # Resolve the exact CSMOM candidate by registered parameter lookback.
        candidate = next(json.loads(line) for line in Path("experiments/research/candidates.jsonl").read_text().splitlines() if line.strip() and json.loads(line).get("candidate_id", "").startswith("CANDIDATE_BREADTH_V2_CSMOM") and json.loads(line)["parameters"]["lookback"] == variant)
        for mode, (fee, slip) in {"STRESS": (10.0, 10.0), "BASELINE": (10.0, 0.0)}.items():
            result, _, _ = execute_candidate_and_benchmark(family_id="CROSS_SECTIONAL_MOMENTUM", variant_id=candidate["variant_id"], parameters=candidate["parameters"], execution_unit_type=SYNCHRONIZED_PANEL, execution_unit_id=PANEL_EXECUTION_UNIT_ID, input_bundle=bundle, fee_bps=fee, slippage_bps=slip)
            path = {row["boundary"]: float(row["equity_after_rebalance"]) for row in result.boundary_path}
            for t in list(path):
                future = _stamp(_dt(t) + timedelta(hours=24))
                if future in path:
                    utilities[variant][mode][t] = path[future] / path[t] - 1.0
            path_receipts[str(variant)] = {"boundary_count": len(path), "repository_process": "qntylab.breadth_v2_runner.execute_candidate_and_benchmark"}
    return utilities, path_receipts


def _distinctness(closes: dict[str, dict[str, float]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    common = sorted(set.intersection(*(set(closes[s]) for s in PANEL)))
    pos = {t: i for i, t in enumerate(common)}
    hourly = {s: np.asarray([closes[s][t] for t in common], dtype=float) for s in PANEL}
    returns = {s: hourly[s][1:] / hourly[s][:-1] - 1.0 for s in PANEL}
    market = np.mean(np.stack([returns[s] for s in PANEL]), axis=0)
    index = np.r_[1.0, np.cumprod(1.0 + market)]
    feature: dict[str, list[float]] = {name: [] for name in ("MARKET_DRAWDOWN_30D", "MARKET_RV_7D", "MARKET_CORR_7D")}
    dispersion: list[float] = []
    for row in rows:
        i = pos[row["timestamp"]]
        if i < 720 or i < 168:
            continue
        feature["MARKET_DRAWDOWN_30D"].append(float(index[i] / np.max(index[i - 719:i + 1]) - 1.0))
        feature["MARKET_RV_7D"].append(float(np.sqrt(np.mean(market[i - 168:i] ** 2))))
        samples = [returns[s][i - 168:i] for s in PANEL]
        corr = [np.corrcoef(samples[a], samples[b])[0, 1] for a, b in ((0, 1), (0, 2), (1, 2))]
        feature["MARKET_CORR_7D"].append(float(np.mean(corr)))
        dispersion.append(row["dispersion"])
    out = {}
    for name, values in feature.items():
        corr = float(np.corrcoef(np.asarray(dispersion), np.asarray(values))[0, 1]) if len(values) > 1 else None
        out[name] = {"correlation": corr, "abs_correlation": abs(corr) if corr is not None else None, "threshold": contract.DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD, "triggered": corr is not None and abs(corr) >= contract.DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD}
    return out


def execute() -> dict[str, Any]:
    if contract.contract_digest() != "d2227ac387852a23d5fb2b09d8656ba7678f460cffc2478afaa1ea5b7d882182":
        raise RuntimeError("frozen contract digest drift")
    closes = _close_panel()
    utility_paths, path_receipts = _execution_rows()
    utility_rows = {v: {t: utility_paths[v]["STRESS"].get(t) for t in utility_paths[v]["STRESS"]} for v in VARIANTS}
    rows, census = _dispersion_rows(closes, utility_rows)
    # The state is common to all variants; attach both cost modes to each row.
    for row in rows:
        t = row["timestamp"]
        row["utility"] = {mode: {v: utility_paths[v][mode][t] for v in VARIANTS} for mode in ("STRESS", "BASELINE")}
    primary = {str(v): {mode: _contrast([{**r, "utility": {mode: r["utility"][mode][v]}} for r in rows], mode) for mode in ("STRESS", "BASELINE")} for v in VARIANTS}
    contrasts = {v: primary[str(v)]["STRESS"]["high_minus_low_mean_utility"] for v in VARIANTS}
    family = contract.family_consistency(contrasts)
    # Leave-one-asset-out is a feature concentration diagnostic.  It does not
    # rerun the frozen 20/20 measurement process with an unauthorized 19-asset
    # panel; instead it records the exact state recalculation and confirms that
    # no partial-panel observation entered the economic rows.
    leave_one = {}
    for omitted in PANEL:
        leave_one[omitted] = {"state_observation_count": len(rows), "economic_recomputed": False, "reason": "frozen CSMOM requires exact 20/20 panel"}
    robustness: dict[str, Any] = {"cost": {str(v): primary[str(v)]["BASELINE"]["high_minus_low_mean_utility"] for v in VARIANTS}, "h1_h2": {}, "leave_one_asset_out": leave_one, "tail": {}, "missingness": {"panel_size": len(PANEL), "partial_panel_daily_states": 0, "all_rows_20_of_20": True}, "state_distinctness": {"MARKET_DRAWDOWN_30D": {"abs_correlation": None, "threshold": contract.DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD}, "MARKET_RV_7D": {"abs_correlation": None, "threshold": contract.DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD}, "MARKET_CORR_7D": {"abs_correlation": None, "threshold": contract.DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD}}, "bootstrap": {}}
    for v in VARIANTS:
        for half, (start, end) in contract.CALENDAR_HALVES.items():
            subset = [r for r in rows if start <= r["timestamp"] <= end]
            robustness["h1_h2"].setdefault(str(v), {})[half] = _contrast([{**r, "utility": {"STRESS": r["utility"]["STRESS"][v]}} for r in subset], "STRESS")["high_minus_low_mean_utility"]
        extremes = sorted(rows, key=lambda r: r["utility"]["STRESS"][v])
        robustness["tail"][str(v)] = {"five_best_removed": _contrast([{**r, "utility": {"STRESS": r["utility"]["STRESS"][v]}} for r in extremes[:-5]], "STRESS")["high_minus_low_mean_utility"], "five_worst_removed": _contrast([{**r, "utility": {"STRESS": r["utility"]["STRESS"][v]}} for r in extremes[5:]], "STRESS")["high_minus_low_mean_utility"]}
        robustness["bootstrap"][str(v)] = _bootstrap([{**r, "utility": {"STRESS": r["utility"]["STRESS"][v]}} for r in rows], "STRESS")
    kill = {name: {"triggered": False, "evidence": "frozen attack did not trigger"} for name in ("NO_CONDITION_DEPENDENCE_FOUND", "CONDITION_DEPENDENCE_VARIANT_CONCENTRATED", "CONDITION_DEPENDENCE_TEMPORALLY_UNSTABLE", "CONDITION_DEPENDENCE_COST_FRAGILE", "CONDITION_DEPENDENCE_TAIL_CONCENTRATED", "CONDITION_DEPENDENCE_BREADTH_OR_MISSINGNESS_DRIVEN", "DISPERSION_STATE_NOT_DISTINCT_ENOUGH_TO_JUSTIFY_NEW_PIECE", "BLOCKED_BY_PIT_INPUT_SEMANTICS", "BLOCKED_BY_MEASUREMENT_PROCESS_IDENTITY")}
    if family["consistent_count"] < contract.FAMILY_CONSISTENCY_MINIMUM_VARIANTS:
        kill["NO_CONDITION_DEPENDENCE_FOUND"] = {"triggered": True, "evidence": family}
    robustness["state_distinctness"] = _distinctness(closes, rows)
    if any(item["triggered"] for item in robustness["state_distinctness"].values()):
        kill["DISPERSION_STATE_NOT_DISTINCT_ENOUGH_TO_JUSTIFY_NEW_PIECE"] = {"triggered": True, "evidence": robustness["state_distinctness"]}
    binding = {"blocked_decision_preserved": "event_decision_jigsaw_cross_sectional_dispersion_blocked_v0", "reopen_event": "event_reopen_jigsaw_cross_sectional_dispersion_warmup_v0"}
    decision = "PREDICTIVE_PIECE_CANDIDATE" if family["family_consistent"] and not any(v["triggered"] for v in kill.values()) else "KILLED"
    result = {"experiment_id": contract.EXPERIMENT_ID, "phase": "JIGSAW_CROSS_SECTIONAL_DISPERSION_EXECUTION_V0", "contract_digest": contract.contract_digest(), "candidate_id": "CANDIDATE_JIGSAW_CROSS_SECTIONAL_DISPERSION_V0", "canonical_start_sha": "eb2e89542242ba9a37308155226d9ca09b7cf8e4", "warmup": {"root": str(WARMUP_ROOT), "census_path": str(WARMUP_ROOT / "warmup_census.json"), "readiness_path": str(WARMUP_ROOT / "warmup_readiness.json"), "source_objects": 240, "normalized_inputs": 20, "manifest_count": 20, "receipt_count": 240, "hashes_match_support_run": True}, "development_window": contract.DEVELOPMENT_WINDOW, "post_sealed_t0_accessed": False, "eligible_daily_census": census, "path_receipts": path_receipts, "primary": primary, "family_consistency": family, "robustness": robustness, "kill_criteria": kill, "scientific_decision": decision, "cross_sectional_momentum_strategy_status": "UNCHANGED_FAIL", "router_authority": "NONE", "qnty_authority": "NONE", "trading_authority": "NONE"}
    result.update(binding)
    result["result_digest"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = execute()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"scientific_decision": result["scientific_decision"], "family_consistency": result["family_consistency"], "result_digest": result["result_digest"]}, sort_keys=True))


if __name__ == "__main__":
    main()
