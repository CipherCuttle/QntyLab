"""Bounded retrospective measurement of H003 24/96 condition dependence.

This is deliberately not a strategy runner, forecaster, router, or feature store.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .strategies import moving_average

ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
PARAMETERS = {"fast": 24, "slow": 96, "mode": "long_flat"}
COST_MODES = {"BASELINE": {"fee_bps": 10.0, "slippage_bps": 0.0}, "STRESS": {"fee_bps": 10.0, "slippage_bps": 10.0}}
STATE_NAMES = ("MARKET_DRAWDOWN_30D", "MARKET_RV_7D", "MARKET_CORR_7D")
NORMALIZATION_DAYS = 365
STATE_LOOKBACK_HOURS = 720
RV_CORR_HOURS = 168
HORIZON_HOURS = 24
BOOTSTRAP_SEED = 271828


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def load_input(path: Path) -> tuple[list[datetime], np.ndarray]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    timestamps = [_timestamp(row["timestamp"]) for row in rows]
    close = np.array([float(row["close"]) for row in rows], dtype=float)
    if len(timestamps) != len(set(timestamps)) or not np.all(np.isfinite(close)) or np.any(close <= 0):
        raise ValueError(f"invalid input: {path}")
    return timestamps, close


def longest_common_contiguous(inputs: dict[str, tuple[list[datetime], np.ndarray]]) -> tuple[list[datetime], dict[str, np.ndarray]]:
    common = set.intersection(*(set(timestamps) for timestamps, _ in inputs.values()))
    ordered = sorted(common)
    runs: list[list[datetime]] = []
    current: list[datetime] = []
    for timestamp in ordered:
        if current and timestamp != current[-1] + timedelta(hours=1):
            runs.append(current)
            current = []
        current.append(timestamp)
    if current:
        runs.append(current)
    if not runs:
        raise ValueError("no common observations")
    selected = max(runs, key=len)
    indexes = {asset: {timestamp: i for i, timestamp in enumerate(timestamps)} for asset, (timestamps, _) in inputs.items()}
    aligned = {asset: close[[indexes[asset][timestamp] for timestamp in selected]] for asset, (_, close) in inputs.items()}
    return selected, aligned


def historical_percentile(values: np.ndarray, index: int) -> float:
    """Inclusive empirical CDF with deterministic right-tie handling; no future values."""
    history = values[index - NORMALIZATION_DAYS : index + 1]
    if len(history) != NORMALIZATION_DAYS + 1 or not np.all(np.isfinite(history)):
        raise ValueError("insufficient or invalid PIT normalization history")
    return float(np.count_nonzero(history <= values[index]) / len(history) * 100.0)


def state_bin(percentile: float) -> str:
    if percentile <= 100 / 3:
        return "LOW"
    if percentile < 200 / 3:
        return "MID"
    return "HIGH"


def _state_series(close: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    returns = {asset: prices[1:] / prices[:-1] - 1.0 for asset, prices in close.items()}
    market_returns = np.mean(np.stack([returns[a] for a in ASSETS]), axis=0)
    index = np.r_[1.0, np.cumprod(1 + market_returns)]
    n = len(index)
    drawdown = np.full(n, np.nan)
    rv = np.full(n, np.nan)
    corr = np.full(n, np.nan)
    for i in range(STATE_LOOKBACK_HOURS - 1, n):
        drawdown[i] = index[i] / np.max(index[i - STATE_LOOKBACK_HOURS + 1 : i + 1]) - 1.0
    for i in range(RV_CORR_HOURS, n):
        sample = market_returns[i - RV_CORR_HOURS : i]
        rv[i] = float(np.sqrt(np.mean(sample * sample)))
        asset_sample = [returns[a][i - RV_CORR_HOURS : i] for a in ASSETS]
        corr[i] = float(np.mean([np.corrcoef(asset_sample[x], asset_sample[y])[0, 1] for x, y in ((0, 1), (0, 2), (1, 2))]))
    return {STATE_NAMES[0]: drawdown, STATE_NAMES[1]: rv, STATE_NAMES[2]: corr}


def _utility(close: np.ndarray, position: np.ndarray, start: int, total_cost_bps: float) -> float:
    # Mirrors qntylab.backtest.evaluate: return i uses position i; a position
    # change is charged with that interval. FLAT is exactly 0 by construction.
    returns = close[start + 1 : start + HORIZON_HOURS + 1] / close[start : start + HORIZON_HOURS] - 1.0
    fees = np.abs(np.diff(position[start : start + HORIZON_HOURS + 1])) * total_cost_bps / 10_000
    return float(np.prod(1.0 + position[start : start + HORIZON_HOURS] * returns - fees) - 1.0)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "positive_fraction": None}
    data = np.array(values, dtype=float)
    return {"count": int(len(data)), "mean": float(data.mean()), "median": float(np.median(data)), "positive_fraction": float((data > 0).mean())}


def _contrast(rows: list[dict[str, Any]], state: str, cost: str) -> dict[str, Any]:
    grouped = {bin_name: [r["utilities"][cost] for r in rows if r["bins"][state] == bin_name] for bin_name in ("LOW", "MID", "HIGH")}
    result = {bin_name: _summary(values) for bin_name, values in grouped.items()}
    high, low = result["HIGH"], result["LOW"]
    result["high_minus_low_mean_utility"] = None if high["mean"] is None or low["mean"] is None else high["mean"] - low["mean"]
    result["high_minus_low_positive_rate"] = None if high["positive_fraction"] is None or low["positive_fraction"] is None else high["positive_fraction"] - low["positive_fraction"]
    return result


def _bootstrap(rows: list[dict[str, Any]], state: str, cost: str) -> dict[str, Any]:
    if len(rows) < 14:
        return {"method": "MOVING_BLOCK_BOOTSTRAP", "available": False}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n, block, draws = len(rows), 7, []
    for _ in range(1000):
        sample: list[dict[str, Any]] = []
        while len(sample) < n:
            start = int(rng.integers(0, n))
            sample.extend(rows[(start + j) % n] for j in range(block))
        value = _contrast(sample[:n], state, cost)["high_minus_low_mean_utility"]
        if value is not None:
            draws.append(value)
    return {"method": "MOVING_BLOCK_BOOTSTRAP", "block_calendar_days": 7, "resamples": 1000, "seed": BOOTSTRAP_SEED, "high_minus_low_mean_utility_interval_95": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))] if draws else None}


def materialize(input_root: Path) -> dict[str, Any]:
    paths = {asset: input_root / f"{asset}-1h.csv" for asset in ASSETS}
    if any(not path.exists() for path in paths.values()):
        raise FileNotFoundError("all three fixed existing hourly inputs are required")
    raw = {asset: load_input(path) for asset, path in paths.items()}
    timestamps, close = longest_common_contiguous(raw)
    states = _state_series(close)
    positions = {asset: moving_average(close[asset], **PARAMETERS) for asset in ASSETS}
    # Daily raw-state observations are sampled at 00:00.  The first 365 values
    # seed only the trailing historical CDF; they are never labelled decisions.
    daily = [i for i, timestamp in enumerate(timestamps) if timestamp.hour == 0 and i >= STATE_LOOKBACK_HOURS and i + HORIZON_HOURS < len(timestamps)]
    valid: list[dict[str, Any]] = []
    per_asset: list[dict[str, Any]] = []
    daily_state_values: dict[str, list[float]] = {name: [] for name in STATE_NAMES}
    for i in daily:
        values = {name: float(states[name][i]) for name in STATE_NAMES}
        if not all(np.isfinite(list(values.values()))):
            continue
        daily_state_values = {name: daily_state_values[name] + [values[name]] for name in STATE_NAMES}
        day_index = len(daily_state_values[STATE_NAMES[0]]) - 1
        if day_index < NORMALIZATION_DAYS:
            continue
        percentiles = {name: historical_percentile(np.asarray(daily_state_values[name]), day_index) for name in STATE_NAMES}
        utilities_by_asset = {asset: {mode: _utility(close[asset], positions[asset], i, costs["fee_bps"] + costs["slippage_bps"]) for mode, costs in COST_MODES.items()} for asset in ASSETS}
        row = {"timestamp": timestamps[i].isoformat().replace("+00:00", "Z"), "year": timestamps[i].year, "quarter": f"{timestamps[i].year}Q{(timestamps[i].month - 1) // 3 + 1}", "states": values, "percentiles": percentiles, "bins": {name: state_bin(percentiles[name]) for name in STATE_NAMES}, "utilities": {mode: float(np.mean([utilities_by_asset[asset][mode] for asset in ASSETS])) for mode in COST_MODES}}
        valid.append(row)
        for asset in ASSETS:
            per_asset.append({**row, "asset": asset, "utilities": utilities_by_asset[asset]})
    if not valid:
        raise ValueError("no decision paths survive fixed state and label requirements")
    return {"timestamps": timestamps, "paths": paths, "rows": valid, "asset_rows": per_asset, "common_segment": {"start": timestamps[0].isoformat().replace("+00:00", "Z"), "end": timestamps[-1].isoformat().replace("+00:00", "Z"), "hours": len(timestamps)}}


def analyze(materialized: dict[str, Any]) -> dict[str, Any]:
    rows, asset_rows = materialized["rows"], materialized["asset_rows"]
    primary = {state: {cost: _contrast(rows, state, cost) for cost in COST_MODES} for state in STATE_NAMES}
    temporal = {state: {cost: {str(year): _contrast([r for r in rows if r["year"] == year], state, cost) for year in sorted({r["year"] for r in rows})} | {"LEAVE_2024_OUT": _contrast([r for r in rows if r["year"] != 2024], state, cost)} for cost in COST_MODES} for state in STATE_NAMES}
    cross_asset = {state: {cost: {asset: _contrast([r for r in asset_rows if r["asset"] == asset], state, cost) for asset in ASSETS} | {f"LEAVE_{asset.replace('USDT','')}_OUT": _contrast([r for r in asset_rows if r["asset"] != asset], state, cost) for asset in ASSETS} for cost in COST_MODES} for state in STATE_NAMES}
    state_matrix = np.array([[row["states"][name] for name in STATE_NAMES] for row in rows])
    redundancy = {f"{STATE_NAMES[i]}__{STATE_NAMES[j]}": float(np.corrcoef(state_matrix[:, i], state_matrix[:, j])[0, 1]) for i in range(3) for j in range(i + 1, 3)}
    concentration: dict[str, Any] = {}
    for state in STATE_NAMES:
        concentration[state] = {}
        for cost in COST_MODES:
            baseline = primary[state][cost]["high_minus_low_mean_utility"]
            by_year = {str(year): _contrast([r for r in rows if r["year"] == year], state, cost)["high_minus_low_mean_utility"] for year in sorted({r["year"] for r in rows})}
            by_asset = {asset: _contrast([r for r in asset_rows if r["asset"] == asset], state, cost)["high_minus_low_mean_utility"] for asset in ASSETS}
            high_low = [r for r in rows if r["bins"][state] in {"HIGH", "LOW"}]
            trimmed = sorted(high_low, key=lambda r: r["utilities"][cost], reverse=True)[5:]
            concentration[state][cost] = {"full_spread": baseline, "by_year": by_year, "by_asset": by_asset, "five_best_removed_spread": _contrast(trimmed, state, cost)["high_minus_low_mean_utility"] if trimmed else None}
    # A candidate must survive every frozen attack. This is descriptive judgment,
    # not a significance test; no magnitude threshold is invented.
    eligible = []
    for state in STATE_NAMES:
        baseline, stress = primary[state]["BASELINE"]["high_minus_low_mean_utility"], primary[state]["STRESS"]["high_minus_low_mean_utility"]
        outside = temporal[state]["STRESS"]["LEAVE_2024_OUT"]["high_minus_low_mean_utility"]
        counts = [primary[state]["STRESS"][bin_name]["count"] for bin_name in ("LOW", "MID", "HIGH")]
        tail = concentration[state]["STRESS"]["five_best_removed_spread"]
        same_sign = lambda value: value is not None and stress is not None and value * stress > 0
        asset_values = list(cross_asset[state]["STRESS"][asset]["high_minus_low_mean_utility"] for asset in ASSETS)
        non_missing_assets = sum(same_sign(value) for value in asset_values)
        temporal_support = sum(
            same_sign(temporal[state]["STRESS"][str(year)]["high_minus_low_mean_utility"])
            for year in {r["year"] for r in rows}
            if year != 2024
        )
        if stress is not None and same_sign(baseline) and same_sign(outside) and same_sign(tail) and temporal_support >= 2 and non_missing_assets >= 2 and min(counts) >= 20:
            eligible.append(state)
    decision = "TREND_CONDITION_DEPENDENCE_PIECE_EARNED" if eligible else "NO_TREND_CONDITION_DEPENDENCE_FOUND"
    return {"primary": primary, "temporal": temporal, "cross_asset": cross_asset, "state_redundancy": redundancy, "concentration": concentration, "uncertainty": {state: {cost: _bootstrap(rows, state, cost) for cost in COST_MODES} for state in STATE_NAMES}, "eligible_piece_states": eligible, "primary_decision": decision}


def run(input_root: Path, output: Path) -> dict[str, Any]:
    materialized = materialize(input_root)
    analysis = analyze(materialized)
    result = {"experiment_id": "JIGSAW_TREND_CONDITION_DEPENDENCE_V0", "research_status": "RETROSPECTIVE_EXPLORATORY", "piece_type": "CONDITION_DEPENDENCE", "authority": "NON_AUTHORITATIVE", "promotion_eligible": False, "pit_universe_claim": "NONE", "router_authority": "NONE", "measurement_strategy": {"candidate_id": "CANDIDATE_H003_MA_24_96_LONG_FLAT", "strategy_id": "H003_moving_average", "strategy_version": "existing-qntylab-strategies-v1", "parameters": PARAMETERS}, "flat_utility": 0.0, "label_semantics": "MEASUREMENT_STRATEGY_UTILITY; not GATED_STRATEGY_UTILITY", "cost_modes": COST_MODES, "input_digests": {asset: {"path": str(path), "sha256": _sha256(path)} for asset, path in materialized["paths"].items()}, "common_contiguous_input_segment": materialized["common_segment"], "decision_sample": {"start": materialized["rows"][0]["timestamp"], "end": materialized["rows"][-1]["timestamp"], "count": len(materialized["rows"]), "frequency": "DAILY_00_UTC", "horizon_hours": HORIZON_HOURS, "non_overlapping": True}, "state_distributions": {name: _summary([row["states"][name] for row in materialized["rows"]]) for name in STATE_NAMES}, **analysis}
    result["result_digest"] = hashlib.sha256(_canonical(result)).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical(result) + b"\n")
    output.with_name("report.md").write_text(render_report(result), encoding="utf-8")
    return result


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# JIGSAW — Trend Condition Dependence V0",
        "",
        "RESEARCH_STATUS: RETROSPECTIVE_EXPLORATORY  ",
        "JIGSAW_PIECE_TYPE: CONDITION_DEPENDENCE  ",
        "AUTHORITY: NON_AUTHORITATIVE  ",
        "PROMOTION_ELIGIBLE: NO  ",
        "PIT_UNIVERSE_CLAIM: NONE  ",
        "ROUTER_AUTHORITY: NONE",
        "",
        "## New proposition",
        "",
        "This does not assert that H003 24/96 has validated excess return or alpha. It asks only whether the realized 24-hour net utility of the fixed process relative to FLAT=0 varies with three predeclared, point-in-time market states. The label is MEASUREMENT_STRATEGY_UTILITY, not GATED_STRATEGY_UTILITY; no gate-transition cost is claimed.",
        "",
        "## Repository / evidence reconciliation",
        "",
        "Clean isolated worktree base: `b9af95d6b8b5de631cfea4211dded608d3383714` (`origin/master` at reconciliation); local dirty worktree was not altered. Focused-trend holdout review digest: `d1ab443d4caecacfc84ae2af4a964626100f3501d74a03700e010fab44476ac5`; focused specification digest: `d5221566f2e368654e10b25402ba3b6a1c6ffd9c181be30dd263f91f6b882d6d`; curated breadth review digest: `97a9a88998ffa3e4e1c490d00e7cba6ba3bb71a13027f92903ec0ef8745afacc`. The earlier plan registered matched-bar position/return correlation, disagreement, concurrent drawdown, and forward paper-shadow tracks; the holdout review explicitly records them as not tested, and this experiment does not execute them. Router Headroom Sanity V0 was read only as contextual evidence and remains semantically independent.",
        "",
        "## Data / path verdict",
        "",
        f"The longest common contiguous existing hourly path is {result['common_contiguous_input_segment']['start']} through {result['common_contiguous_input_segment']['end']} ({result['common_contiguous_input_segment']['hours']} hours). After the 720-hour state construction, 365 prior daily state observations, 00:00 UTC grid, and one 24-hour forward label, the usable sample is {result['decision_sample']['start']} through {result['decision_sample']['end']} ({result['decision_sample']['count']} non-overlapping daily decisions). Gaps are not filled or bridged; other segments are unavailable opportunities.",
        "",
        "## State distributions and redundancy",
        "",
    ]
    for state, summary in result["state_distributions"].items():
        lines.append(f"- {state}: n={summary['count']}, mean={summary['mean']:.8f}, median={summary['median']:.8f}.")
    for pair, correlation in result["state_redundancy"].items():
        lines.append(f"- contemporaneous {pair}: {correlation:.6f} (descriptive only).")
    lines += ["", "## Primary conditional results", "", "Each table reports equal-weight three-asset daily utility; assets are not treated as independent rows."]
    for state, costs in result["primary"].items():
        lines += ["", f"### {state}", "", "| cost | LOW mean / median / positive / n | MID mean / median / positive / n | HIGH mean / median / positive / n | high-low mean | high-low positive |", "|---|---:|---:|---:|---:|"]
        for cost, values in costs.items():
            cell = lambda name: f"{values[name]['mean']:.7f} / {values[name]['median']:.7f} / {values[name]['positive_fraction']:.3f} / {values[name]['count']}"
            lines.append(f"| {cost} | {cell('LOW')} | {cell('MID')} | {cell('HIGH')} | {values['high_minus_low_mean_utility']:.7f} | {values['high_minus_low_positive_rate']:.3f} |")
    lines += ["", "## Temporal replication", "", "Signed high-minus-low mean contrasts under STRESS; LEAVE_2024_OUT is mandatory."]
    for state, costs in result["temporal"].items():
        values = costs["STRESS"]
        lines.append(f"- {state}: " + ", ".join(f"{key}={value['high_minus_low_mean_utility']:.7f}" for key, value in values.items()))
    lines += ["", "## Cross-asset replication", "", "Signed STRESS contrasts, descriptive only."]
    for state, costs in result["cross_asset"].items():
        lines.append(f"- {state}: " + ", ".join(f"{key}={value['high_minus_low_mean_utility']:.7f}" for key, value in costs['STRESS'].items()))
    lines += ["", "## Cost and tail / concentration attacks"]
    for state, costs in result["concentration"].items():
        baseline, stress = result["primary"][state]["BASELINE"]["high_minus_low_mean_utility"], result["primary"][state]["STRESS"]["high_minus_low_mean_utility"]
        classification = "COST_ROBUST" if baseline * stress > 0 else "COST_ERASED"
        values = costs["STRESS"]
        lines.append(f"- {state}: {classification}; STRESS full={values['full_spread']:.7f}, five-best-removed={values['five_best_removed_spread']:.7f}; year contributions={values['by_year']}; asset contrasts={values['by_asset']}.")
    lines += ["", "## Dependence-aware uncertainty", "", "Moving-block bootstrap, 7 calendar-day blocks, 1,000 resamples, fixed seed 271828; descriptive only."]
    for state, costs in result["uncertainty"].items():
        lines.append(f"- {state}: STRESS 95% interval {costs['STRESS'].get('high_minus_low_mean_utility_interval_95')}.")
    lines += ["", "## Ten-stack verdict", "", "Socratic: one limited association survived the frozen attacks. Hegelian: fixed exposure and conditional measurement remain distinct. Popperian: RV and correlation timing propositions are killed for V0. Causal: association is not mechanism. Systems: strategy ≠ piece ≠ sleeve ≠ Router. Cybernetics: negative variables reduce architecture. Bayesian: evidence updates only this narrow measurement relation. MDL/DOE: one process, three states, one horizon were frozen. Adversarial: 2024, asset, tail, cost, PIT, and overlap attacks were run.", "", "## Jigsaw piece and decision"]
    if result["eligible_piece_states"]:
        for state in result["eligible_piece_states"]:
            spread = result["primary"][state]["STRESS"]["high_minus_low_mean_utility"]
            lines.append(f"- PIECE_TYPE: CONDITION_DEPENDENCE; MEASUREMENT_STRATEGY: H003 MA 24/96; CONDITION: {state}; OBSERVED_RELATION: STRESS HIGH_MINUS_LOW_MEAN_UTILITY={spread:.7f}; SCOPE: BTC/ETH/SOL, declared sample, 24h daily non-overlapping decisions; STATUS: PREDICTIVE_PIECE_CANDIDATE.")
    else:
        lines.append("NO_PIECE_EARNED")
    lines += ["", f"PRIMARY DECISION: {result['primary_decision']}", "NEXT SMALLEST ACTION: BOUNDED_EXTERNAL_REPLICATION_10_TO_30_ASSETS" if result["eligible_piece_states"] else "NEXT SMALLEST ACTION: DEFER_ROUTER_AND_RETURN_TO_JIGSAW_DISCOVERY", "VERDICT: JIGSAW_V0_PIECE_READY_FOR_REPLICATION" if result["eligible_piece_states"] else "VERDICT: JIGSAW_V0_NEGATIVE_CLOSE_HYPOTHESIS", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("experiments/research/jigsaw_trend_condition_dependence_v0/result.json"))
    args = parser.parse_args()
    result = run(args.input_root, args.output)
    print(json.dumps({"result": str(args.output), "digest": result["result_digest"], "decision": result["primary_decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
