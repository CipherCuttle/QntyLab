"""Deterministic, local-only executor for the frozen Sprint-v2 contract.

This module deliberately has no network capability.  Its command line entry
point is for the next blind execution agent; tests exercise it only with
synthetic :class:`~qntylab.sprint_v2.FrozenInputs` fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .sprint_v2 import DATASET_ROOT_SHA256, INVENTORY_SHA256, LEDGER_SHA256, UNION_SHA256, EXPECTED_FACTORS, FrozenInputs, materialize

IDENTITY = "EXPLORATORY ONLY; NON_AUTHORITATIVE; FROZEN PRE-OUTCOME EXECUTION; NO PAPER/LIVE AUTHORITY; NO TRADING EXECUTION"
MINIMUM_BREADTH, FRACTION = 10, 0.2
UNRESOLVED = "UNRESOLVED_CLASSIFICATION_SEMANTIC"


def _json(value: Any) -> Any:
    """Convert numpy values and non-finite floats to canonical JSON values."""
    if isinstance(value, np.ndarray): return [_json(x) for x in value.tolist()]
    if isinstance(value, (np.floating, float)): return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, dict): return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_json(x) for x in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_semantic_closure(root: Path) -> dict[str, Any]:
    """Fail closed unless the immutable spec/amendment bindings are exact."""
    spec_bytes = (root / "experiments/specs/sprint_v2_cross_sectional.json").read_bytes()
    closure = json.loads((root / "experiments/specs/sprint_v2_pre_outcome_semantic_closure_001.json").read_text())
    manifest_bytes = (root / "experiments/data/sprint_v2_pre_outcome_dataset_manifest.json").read_bytes()
    expected = {
        "original_preregistration_commit": "b5c4f1622c19c442cfe5c30b84ebcd9d2a95b445",
        "dataset_freeze_commit": "5ae7336f9b24369d2a7cb7f4ceb6474fb450e85b",
        "input_harness_commit": "53fe4d31a30182d8b06ac2cf9e0c67ea636a6915",
        "original_spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "dataset_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    if any(closure.get(key) != value for key, value in expected.items()):
        raise ValueError("semantic closure binding mismatch")
    if closure.get("outcomes_observed_before_amendment") is not False or closure.get("scientific_parameters_changed") is not False:
        raise ValueError("semantic closure pre-outcome binding invalid")
    if closure.get("closure_gates", {}).get("EXECUTION_SEMANTICS_COMPLETE") is not True:
        raise ValueError("execution semantics are not closed")
    if closure.get("classification_semantics", {}).get("unresolved_status") != UNRESOLVED:
        raise ValueError("classification closure binding invalid")
    return closure


def _adjacent(a: str, b: str) -> bool:
    return date.fromisoformat(b) == date.fromisoformat(a) + timedelta(days=1)


def _book(symbols: tuple[str, ...], score: np.ndarray, eligible: np.ndarray, direction: int) -> np.ndarray:
    available = [i for i, symbol in enumerate(symbols) if eligible[i] and np.isfinite(score[i])]
    available.sort(key=lambda i: (-float(score[i]), symbols[i]))
    n, k = len(available), max(1, int(np.floor(FRACTION * len(available))))
    result = np.zeros(len(symbols), dtype=float)
    if n < MINIMUM_BREADTH or n < 2 * k: return result
    result[available[:k]] = direction / k
    result[available[-k:]] = -direction / k
    return result


def _spearman(symbols: tuple[str, ...], score: np.ndarray, forward: np.ndarray, eligible: np.ndarray) -> float:
    ix = [i for i, symbol in enumerate(symbols) if eligible[i] and np.isfinite(score[i]) and np.isfinite(forward[i])]
    if len(ix) < 2: return float("nan")
    # Stable ordinal ranks after lexicographic ordering: ties are intentionally
    # assigned distinct ranks in deterministic symbol order, as frozen.
    sx = sorted(ix, key=lambda i: (float(score[i]), symbols[i])); sy = sorted(ix, key=lambda i: (float(forward[i]), symbols[i]))
    xrank = {item: rank for rank, item in enumerate(sx)}; yrank = {item: rank for rank, item in enumerate(sy)}
    x = np.array([xrank[i] for i in ix], float); y = np.array([yrank[i] for i in ix], float)
    return float(np.corrcoef(x, y)[0, 1]) if x.std() and y.std() else float("nan")


def _events(inputs: FrozenInputs, t: int, weight: np.ndarray) -> tuple[np.ndarray, list[str]]:
    start, end = inputs.dates[t] + "T00:00:00Z", inputs.dates[t + 1] + "T00:00:00Z"
    cash = np.zeros(len(inputs.symbols)); missing: list[str] = []
    for j, symbol in enumerate(inputs.symbols):
        rows = inputs.funding_events.get(symbol)
        if rows is None:
            missing.append(symbol); continue
        settled = False
        for row in rows:
            if start < row["timestamp"] <= end:
                cash[j] -= weight[j] * float(row["funding_rate"]); settled = True
        if weight[j] and not settled: missing.append(symbol)
    return cash, missing


def _summary(records: list[dict[str, Any]], cost: int) -> dict[str, Any]:
    net = np.array([r["price_pnl"] + r["funding_pnl"] - r["fees"][str(cost)] for r in records], float)
    gross = np.array([r["price_pnl"] + r["funding_pnl"] for r in records], float)
    return {"gross_cumulative_return": float(np.prod(1 + gross) - 1), "net_cumulative_return": float(np.prod(1 + net) - 1), "price_pnl": float(sum(r["price_pnl"] for r in records)), "funding_pnl": float(sum(r["funding_pnl"] for r in records)), "fees": float(sum(r["fees"][str(cost)] for r in records)), "turnover": float(sum(r["turnover"] for r in records))}


def _segments(records: list[dict[str, Any]], cost: int) -> dict[str, Any]:
    ranges = {"2020": ("2020-01-01", "2020-12-31"), "2021_2023": ("2021-01-01", "2023-12-31"), "2024_plus": ("2024-01-01", "2026-06-30")}
    out = {name: _summary([r for r in records if lo <= r["date"] <= hi], cost) for name, (lo, hi) in ranges.items()}
    windows = []
    eligible_records = [r for r in records if r["valid_portfolio"] and r["eligible_return_count"] > 0]
    for i in range(max(0, len(eligible_records) - 179)):
        sample = eligible_records[i:i + 180]
        if len(sample) == 180: windows.append({"start": sample[0]["date"], "end": sample[-1]["date"], **_summary(sample, cost)})
    return {"calendar": out, "rolling_180": windows}


def execute_variant(inputs: FrozenInputs, variant: tuple[str, int, int], *, anchor: int | None = None, score: np.ndarray | None = None) -> dict[str, Any]:
    """Execute a single factor or synthetic null panel using only supplied arrays."""
    name, _, direction = variant; panel = inputs.scores[name] if score is None else score
    if panel.shape != inputs.close.shape: raise ValueError("score panel shape mismatch")
    prior = np.zeros(len(inputs.symbols)); records: list[dict[str, Any]] = []; ics: list[dict[str, Any]] = []
    contributions = np.zeros(len(inputs.symbols)); long_contrib = np.zeros(len(inputs.symbols)); short_contrib = np.zeros(len(inputs.symbols))
    for t in range(len(inputs.dates) - 1):
        scheduled = anchor is None or date.fromisoformat(inputs.dates[t]).weekday() == anchor
        target = _book(inputs.symbols, panel[t], inputs.eligible[t], direction) if scheduled else prior.copy()
        # A scheduled weekly date with insufficient finite breadth is not an
        # implicit exit/rebalance.  It retains its last valid book.
        if anchor is not None and scheduled and not np.any(target): target = prior.copy()
        valid_book = bool(np.any(target))
        turn = float(np.abs(target - prior).sum())
        adjacent = _adjacent(inputs.dates[t], inputs.dates[t + 1])
        forward = np.divide(inputs.close[t + 1], inputs.close[t], out=np.full(len(prior), np.nan), where=np.isfinite(inputs.close[t + 1]) & np.isfinite(inputs.close[t])) - 1
        valid_return = adjacent & np.isfinite(forward)
        price_by_asset = np.where(valid_return, target * forward, 0.0)
        forced = np.where((target != 0) & ~valid_return)[0]
        forced_turn = float(np.abs(target[forced]).sum())
        carry, missing_funding = _events(inputs, t, target)
        total_by_asset = price_by_asset + carry
        contributions += total_by_asset; long_contrib += np.where(target > 0, total_by_asset, 0); short_contrib += np.where(target < 0, total_by_asset, 0)
        effective_next = target.copy(); effective_next[forced] = 0.0
        fees = {str(cost): (turn + forced_turn) * cost / 10_000 for cost in inputs.cost_bps}
        records.append({"date": inputs.dates[t], "scheduled": scheduled, "valid_portfolio": valid_book, "eligible_return_count": int(np.count_nonzero((target != 0) & valid_return)), "weights": target.tolist(), "turnover": turn + forced_turn, "price_pnl": float(price_by_asset.sum()), "funding_pnl": float(carry.sum()), "price_pnl_by_asset": price_by_asset.tolist(), "funding_pnl_by_asset": carry.tolist(), "fees": fees, "total_pnl_before_fees": float(total_by_asset.sum()), "forced_close_symbols": [inputs.symbols[i] for i in forced], "funding_source_missing_symbols": missing_funding})
        ics.append({"date": inputs.dates[t], "value": _spearman(inputs.symbols, panel[t], forward if adjacent else np.full_like(forward, np.nan), inputs.eligible[t])})
        prior = effective_next
    finite_ics = [x["value"] for x in ics if np.isfinite(x["value"])]
    cost_reports = {str(cost): _summary(records, cost) for cost in inputs.cost_bps}
    total = float(contributions.sum())
    def shares(values: np.ndarray) -> list[dict[str, Any]]:
        signed = float(values.sum()); denom = signed if signed else float(np.abs(values).sum())
        return [{"symbol": s, "contribution": values[i], "share": (values[i] / denom if denom else 0.0)} for i, s in enumerate(inputs.symbols) if values[i] != 0]
    period_contributions = {}
    for label, lo, hi in (("2020", "2020-01-01", "2020-12-31"), ("2021_2023", "2021-01-01", "2023-12-31"), ("2024_plus", "2024-01-01", "2026-06-30")):
        rows = [r for r in records if lo <= r["date"] <= hi]
        period_contributions[label] = {"total": float(sum(r["total_pnl_before_fees"] for r in rows)), "long": float(sum(sum(p + f for w, p, f in zip(r["weights"], r["price_pnl_by_asset"], r["funding_pnl_by_asset"]) if w > 0) for r in rows)), "short": float(sum(sum(p + f for w, p, f in zip(r["weights"], r["price_pnl_by_asset"], r["funding_pnl_by_asset"]) if w < 0) for r in rows))}
    classification = {"objective_predicates": {"net_10bps_nonpositive": cost_reports["10"]["net_cumulative_return"] <= 0, "positive_10bps": cost_reports["10"]["net_cumulative_return"] > 0, "uninterpretable_delisting": any(r["forced_close_symbols"] for r in records)}, "status": "OBJECTIVE_KILL" if cost_reports["10"]["net_cumulative_return"] <= 0 else UNRESOLVED, "unresolved_semantics": ["incoherent_or_zero_ic", "ordinary_random_rank_outcome", "single_leg_market_beta", "20bps_catastrophic", "breadth_or_180d_instability", "coherent_ic", "multiple_periods", "meaningfully_beats_random", "nearby_variant", "adequate_breadth", "not_one_asset_driven"]}
    return {"variant_id": name, "anchor": anchor, "daily_portfolio_records": records, "cost_reports": cost_reports, "ic": {"daily": ics, "mean": float(np.mean(finite_ics)) if finite_ics else float("nan"), "median": float(np.median(finite_ics)) if finite_ics else float("nan"), "positive_hit_rate": float(np.mean(np.array(finite_ics) > 0)) if finite_ics else float("nan"), "count": len(finite_ics)}, "temporal": {str(cost): _segments(records, cost) for cost in inputs.cost_bps}, "concentration": {"asset": {"total": shares(contributions), "long": shares(long_contrib), "short": shares(short_contrib)}, "period": period_contributions}, "classification": classification}


def execute(inputs: FrozenInputs) -> dict[str, Any]:
    """Run every frozen variant and required diagnostics deterministically."""
    variants = []
    rng = np.random.default_rng(inputs.null_seed)
    for variant in EXPECTED_FACTORS:
        main = execute_variant(inputs, variant)
        weekly = {name: execute_variant(inputs, variant, anchor=weekday) for weekday, name in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))}
        values = [weekly[name]["cost_reports"]["10"]["net_cumulative_return"] for name in weekly]
        null = [execute_variant(inputs, variant, score=rng.random(inputs.close.shape))["cost_reports"] for _ in range(inputs.null_count)]
        main["weekly_robustness"] = {"anchors": weekly, "net_10bps": {"median": float(np.median(values)), "minimum": float(min(values)), "maximum": float(max(values)), "positive_anchor_count": int(sum(x > 0 for x in values)), "dispersion": float(max(values) - min(values))}}
        main["random_rank_null"] = {"seed": inputs.null_seed, "count": inputs.null_count, "draw_cost_reports": null}
        variants.append(main)
    return {"identity": IDENTITY, "frozen_input_identity": {"dataset_root_sha256": DATASET_ROOT_SHA256, "union_selected_sha256": UNION_SHA256, "universe_ledger_sha256": LEDGER_SHA256, "daily_inventory_sha256": INVENTORY_SHA256, "dates": [inputs.dates[0], inputs.dates[-1]], "symbols": list(inputs.symbols), "shape": list(inputs.close.shape)}, "multiple_testing_ledger": {"sprint_v0_result_records": 45, "sprint_v1_result_records": 51, "sprint_v2_planned": 8, "sprint_v2_observed_before_execution": 0}, "variants": variants}


def main() -> None:
    parser = argparse.ArgumentParser(description="execute frozen Sprint-v2 outcomes from local frozen inputs")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); verify_semantic_closure(args.root); result = execute(materialize(args.root))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(canonical_bytes(result))


if __name__ == "__main__": main()
