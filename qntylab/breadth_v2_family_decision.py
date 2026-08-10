"""Deterministic, outcome-free Breadth V2 family decision reducer.

The module consumes already-produced receipt/path-shaped mappings.  It does
not execute strategies, calculate portfolio accounting, or read the ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

CONTRACT_ID = "BREADTH_V2_FAMILY_DECISION_CONTRACT_V0"
SCREEN_ID = "QNTYLAB_BREADTH_V2_20260810"
INPUT_UNIVERSE_CONTRACT = "BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1"
INPUT_UNIVERSE_SHA256 = "8fef4c02d113027630072bcbb0802e35ab31be17c835aa2ebdae4261265589fb"
ASSETS = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT", "XLMUSDT",
    "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT", "ONEUSDT", "API3USDT",
    "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT", "LDOUSDT", "APTUSDT",
)
PERIODS = ("DEV_2022", "DEV_2024", "DEV_2025")
COST_MODES = ("BASELINE_EXECUTION", "STRESS_EXECUTION")
FAMILIES = (
    "TIME_SERIES_MOMENTUM", "MOVING_AVERAGE_TREND", "PRICE_BREAKOUT",
    "CROSS_SECTIONAL_MOMENTUM", "CROSS_SECTIONAL_REVERSAL", "FUNDING_CARRY",
    "VOLATILITY_TARGETING",
)
PANEL_FAMILIES = frozenset(FAMILIES[3:6])
VARIANTS = {
    "TIME_SERIES_MOMENTUM": ("variant_07e9c327cb88170fec74bada", "variant_a64390f22e528b77d8ef59d3", "variant_e169ef767c8bd418c92e1b92", "variant_b1ea26174c6196badbfa543d"),
    "MOVING_AVERAGE_TREND": ("variant_d5f7ee106ba428292feacd0b", "variant_2584eb63c90a1aa65da2e006", "variant_83dc90d06ac8234aaacd575b", "variant_104b54d3f448e98b07bb104f"),
    "PRICE_BREAKOUT": ("variant_ac4a45549606e2d83bad89a9", "variant_057bf9fb96021b54541a31cc", "variant_81f0ae4565fe4e93e8ecfa09", "variant_5910c68e1b751a6d26bda998"),
    "CROSS_SECTIONAL_MOMENTUM": ("variant_7e63843cf5bd2e7a7de4fdad", "variant_7303fa15c85dc51d8a5bafdb", "variant_c792ef713b134324d653429a", "variant_5c7a31cebbfe6506da22180a"),
    "CROSS_SECTIONAL_REVERSAL": ("variant_9eb64776e5ac25ed6a62d119", "variant_ea8018e0c253cee0f01f8223", "variant_b9540e368e55931e1ee6b3c3", "variant_f78077ee5e25b2e98f8e3d50"),
    "FUNDING_CARRY": ("variant_e1c1b40c5a5baaf187bcbe6e", "variant_758b7e3944c259ce13caa9bb", "variant_7731fcf1e274606f8355f71f", "variant_79b83fa77fb52d9fcda6fe9c"),
    "VOLATILITY_TARGETING": ("variant_43e150322c8152220a441247", "variant_0e6d39d7dec66014ed185509", "variant_a176ac3f3a0404c7b56c1d43", "variant_398f69a1a41c6b5c484b0034"),
}
ADJACENCY = {
    family: tuple(zip(VARIANTS[family], VARIANTS[family][1:])) for family in FAMILIES
}
RELATIVE_VALUE_FAMILIES = PANEL_FAMILIES
TOLERANCE = 1e-9


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def contract_manifest() -> dict[str, Any]:
    """Return the timestamp-free, canonical identity material for this contract."""
    return {
        "contract_id": CONTRACT_ID, "registered_screen_id": SCREEN_ID,
        "input_universe_contract": INPUT_UNIVERSE_CONTRACT,
        "input_universe_sha256": INPUT_UNIVERSE_SHA256, "registered_variants": 28,
        "families": list(FAMILIES), "variants": {k: list(v) for k, v in VARIANTS.items()},
        "assets": list(ASSETS), "periods": list(PERIODS), "cost_modes": list(COST_MODES),
        "adjacency_map": {k: [list(pair) for pair in v] for k, v in ADJACENCY.items()},
        "gates": {"positive_windows": 2, "positive_assets": 10, "max_positive_share": 0.35,
                  "neighbour_pairs": 1, "cost_retention": 0.50, "leg_assets": 8},
    }


CONTRACT_DIGEST = _sha(contract_manifest())


def normalize_observation(observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize one runner-shaped execution into one row per asset.

    Panel cells are divided by the receipt's recorded initial equity.  The
    receipt's portfolio totals are reconciled against the sum of those cells.
    """
    required = ("family_id", "variant_id", "period_id", "cost_mode", "execution_unit_type", "execution_unit_id", "input_status", "receipt_valid", "path_valid")
    missing = [key for key in required if key not in observation]
    if missing:
        raise ValueError(f"missing observation fields: {missing}")
    if observation["input_status"] != "READY" or not observation["receipt_valid"] or not observation["path_valid"]:
        return []
    base = {key: observation[key] for key in required}
    if observation["execution_unit_type"] == "SINGLE_ASSET":
        row = dict(base)
        row.update({"asset": observation["asset"], "candidate_net_score": float(observation["candidate_net_return"]), "benchmark_net_score": float(observation["benchmark_net_return"]), "excess_score": float(observation["excess_return_vs_benchmark"])})
        return [row]
    if observation["execution_unit_type"] != "SYNCHRONIZED_PANEL":
        raise ValueError("unknown execution_unit_type")
    receipt = observation.get("receipt", observation)
    initial = receipt.get("candidate_result", {}).get("initial_equity", observation.get("initial_equity"))
    if initial is None or not math.isfinite(float(initial)) or float(initial) == 0:
        raise ValueError("panel initial_equity is required and must be finite/non-zero")
    initial = float(initial)
    cells = observation.get("scientific_cells", receipt.get("scientific_cells", []))
    candidate_final = float(receipt.get("candidate_result", {}).get("final_pnl", observation.get("candidate_final_pnl", 0.0)))
    benchmark_final = float(receipt.get("benchmark_result", {}).get("final_pnl", observation.get("benchmark_final_pnl", 0.0)))
    candidate_sum = sum(float(cell["candidate_net_contribution"]) for cell in cells)
    benchmark_sum = sum(float(cell["benchmark_net_contribution"]) for cell in cells)
    if abs(candidate_sum - candidate_final) > TOLERANCE or abs(benchmark_sum - benchmark_final) > TOLERANCE:
        raise ValueError("panel contribution cells do not reconcile to portfolio totals")
    rows = []
    for cell in cells:
        row = dict(base)
        candidate = float(cell["candidate_net_contribution"]) / initial
        benchmark = float(cell["benchmark_net_contribution"]) / initial
        excess = float(cell["excess_contribution_vs_benchmark"]) / initial
        if abs((candidate - benchmark) - excess) > TOLERANCE:
            raise ValueError("panel excess contribution does not reconcile")
        row.update({"asset": cell["symbol"], "candidate_net_score": candidate, "benchmark_net_score": benchmark, "excess_score": excess})
        rows.append(row)
    return rows


def _status(positive: int, inconclusive: int, threshold: int) -> str:
    if positive >= threshold:
        return "PASS"
    if positive + inconclusive < threshold:
        return "FAIL"
    return "INCONCLUSIVE"


def _integrity(expected: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]], family_id: str) -> list[str]:
    expected_keys = []
    for row in expected:
        if row.get("family_id") == family_id and row.get("input_status") == "READY":
            expected_keys.append(tuple(row.get(k) for k in ("family_id", "variant_id", "execution_unit_type", "execution_unit_id", "period_id", "cost_mode")))
    actual_keys = []
    errors = []
    for row in observations:
        if row.get("family_id") != family_id:
            continue
        key = tuple(row.get(k) for k in ("family_id", "variant_id", "execution_unit_type", "execution_unit_id", "period_id", "cost_mode"))
        actual_keys.append(key)
        if row.get("input_status") == "BLOCKED":
            errors.append("BLOCKED_INPUT_EXECUTION_PRESENT")
        if not row.get("receipt_valid", False): errors.append("RECEIPT_INVALID")
        if not row.get("path_valid", False): errors.append("PATH_INVALID")
        if row.get("evaluation_id") is not None and row.get("evaluation_id") != row.get("recomputed_evaluation_id", row.get("evaluation_id")):
            errors.append("EVALUATION_ID_MISMATCH")
        if row.get("bundle_sha256") is not None and row.get("bundle_sha256") != row.get("expected_bundle_sha256", row.get("bundle_sha256")):
            errors.append("BUNDLE_IDENTITY_MISMATCH")
    if len(actual_keys) != len(set(actual_keys)): errors.append("DUPLICATE_EXECUTION")
    if set(actual_keys) != set(expected_keys):
        errors.extend(["MISSING_READY_EXECUTION"] if set(expected_keys) - set(actual_keys) else [])
        errors.extend(["UNEXPECTED_EXECUTION"] if set(actual_keys) - set(expected_keys) else [])
    return sorted(set(errors))


def _relative_value_diagnostics(observations: Sequence[Mapping[str, Any]], family_id: str) -> tuple[dict[str, int], dict[str, Any], list[str]]:
    long_values: defaultdict[str, float] = defaultdict(float); short_values: defaultdict[str, float] = defaultdict(float); errors: list[str] = []
    exposure = []
    for obs in observations:
        if obs.get("family_id") != family_id or obs.get("cost_mode") != "STRESS_EXECUTION" or not obs.get("path_valid"):
            continue
        prior: Mapping[str, Any] = {}
        for row in obs.get("candidate_path", []):
            weights = row.get("target_weights", {})
            if prior:
                for asset, details in row.get("assets", {}).items():
                    value = float(details.get("price_pnl", 0.0)) + float(details.get("funding_pnl", 0.0))
                    sign = float(prior.get(asset, 0.0))
                    if sign > 0: long_values[asset] += value
                    elif sign < 0: short_values[asset] += value
                active = [float(v) for v in weights.values() if float(v) != 0.0]
                if active:
                    exposure.append({"long_gross": sum(v for v in active if v > 0), "short_gross": sum(v for v in active if v < 0), "gross_absolute": sum(abs(v) for v in active), "net": sum(active)})
            prior = weights
    if exposure and any(abs(x["long_gross"] - 1.0) > TOLERANCE or abs(x["short_gross"] + 1.0) > TOLERANCE or abs(x["gross_absolute"] - 2.0) > TOLERANCE or abs(x["net"]) > TOLERANCE for x in exposure):
        errors.append("BLOCKED_INTEGRITY_EXPOSURE_INVARIANT")
    counts = {"long_positive_assets": sum(v > 0 for v in long_values.values()), "short_positive_assets": sum(v > 0 for v in short_values.values())}
    return counts, {"observed_boundaries": len(exposure), "samples": exposure}, errors


def reduce_family(*, family_id: str, observations: Sequence[Mapping[str, Any]], expected_inputs: Sequence[Mapping[str, Any]], registered_variants: Sequence[str] | None = None, registered_assets: Sequence[str] = ASSETS, registered_periods: Sequence[str] = PERIODS) -> dict[str, Any]:
    """Reduce future observations into one deterministic family receipt."""
    if family_id not in FAMILIES: raise ValueError(f"unregistered family: {family_id}")
    variants = tuple(registered_variants or VARIANTS[family_id])
    integrity_errors = _integrity(expected_inputs, observations, family_id)
    normalized: list[dict[str, Any]] = []
    normalization_errors = []
    for obs in observations:
        if obs.get("family_id") != family_id: continue
        try: normalized.extend(normalize_observation(obs))
        except (KeyError, TypeError, ValueError) as exc: normalization_errors.append(str(exc))
    if normalization_errors: integrity_errors.append("DECISION_INPUT_CONTRACT")
    by_aw: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    score_rows = [row for row in normalized if row["cost_mode"] == "STRESS_EXECUTION"]
    for row in score_rows:
        by_aw[(row["asset"], row["period_id"])].append(row); by_variant[row["variant_id"]].append(row)
    window_scores = {}; pooled = {}
    for period in registered_periods:
        for asset in registered_assets:
            rows = by_aw[(asset, period)]; ex = _mean(r["excess_score"] for r in rows); net = _mean(r["candidate_net_score"] for r in rows)
            window_scores[f"{asset}:{period}"] = {"excess": ex, "net": net, "status": "MISSING" if ex is None else "OBSERVED", "usable_variant_count": len({r["variant_id"] for r in rows}), "blocked_variant_count": len(variants) - len({r["variant_id"] for r in rows}), "registered_variant_count": len(variants)}
    for asset in registered_assets:
        values = [window_scores[f"{asset}:{period}"]["excess"] for period in registered_periods if window_scores[f"{asset}:{period}"]["excess"] is not None]
        value = _mean(values); pooled[asset] = {"excess": value, "status": "INCONCLUSIVE_ASSET" if value is None else ("POSITIVE_ASSET" if value > 0 else "NON_POSITIVE_ASSET"), "observed_window_count": len(values)}
    stress_windows = {}
    for period in registered_periods:
        vals = [window_scores[f"{asset}:{period}"]["excess"] for asset in registered_assets if window_scores[f"{asset}:{period}"]["excess"] is not None]
        value = _mean(vals); stress_windows[period] = {"excess": value, "status": "INCONCLUSIVE" if value is None else ("POSITIVE" if value > 0 else "NON_POSITIVE"), "observed_asset_count": len(vals)}
    temporal = _status(sum(v["status"] == "POSITIVE" for v in stress_windows.values()), sum(v["status"] == "INCONCLUSIVE" for v in stress_windows.values()), 2)
    asset_breadth = _status(sum(v["status"] == "POSITIVE_ASSET" for v in pooled.values()), sum(v["status"] == "INCONCLUSIVE_ASSET" for v in pooled.values()), 10)
    positive_total = sum(v["excess"] for v in pooled.values() if v["excess"] is not None and v["excess"] > 0)
    max_share = max(((v["excess"] / positive_total) for v in pooled.values() if v["excess"] is not None and v["excess"] > 0), default=None)
    concentration = "FAIL" if not positive_total else ("PASS" if max_share <= 0.35 else "FAIL")
    aggregate_values = [v["excess"] for v in window_scores.values() if v["excess"] is not None]
    variant_scores = {variant: {"stress_excess": _mean(r["excess_score"] for r in by_variant[variant]), "stress_net": _mean(r["candidate_net_score"] for r in by_variant[variant]), "usable_observations": len(by_variant[variant]), "blocked_observations": len(registered_assets) * len(registered_periods) - len(by_variant[variant])} for variant in variants}
    qualifying = []
    for left, right in ADJACENCY[family_id]:
        a, b = variant_scores[left], variant_scores[right]
        if a["stress_excess"] is not None and b["stress_excess"] is not None and a["stress_excess"] > 0 and b["stress_excess"] > 0 and a["stress_net"] and b["stress_net"] and ((a["stress_net"] > 0) == (b["stress_net"] > 0)): qualifying.append([left, right])
    all_pairs_observed = all(variant_scores[a]["usable_observations"] == len(registered_assets) * len(registered_periods) and variant_scores[b]["usable_observations"] == len(registered_assets) * len(registered_periods) for a, b in ADJACENCY[family_id])
    neighbourhood = "PASS" if qualifying else ("FAIL" if all_pairs_observed else "INCONCLUSIVE")
    matched = {(r["variant_id"], r["asset"], r["period_id"]): r for r in normalized if r["cost_mode"] == "BASELINE_EXECUTION"}
    stress = {(r["variant_id"], r["asset"], r["period_id"]): r for r in normalized if r["cost_mode"] == "STRESS_EXECUTION"}
    cost_blocked = set(matched) != set(stress) or any(key not in matched or key not in stress for key in matched | stress)
    baseline = _mean(r["excess_score"] for r in matched.values()); stressed = _mean(r["excess_score"] for r in stress.values())
    ratio = stressed / baseline if baseline and stressed is not None and baseline != 0 else None
    cost = "BLOCKED" if cost_blocked else ("PASS" if baseline is not None and stressed is not None and baseline > 0 and stressed > 0 and ratio >= 0.50 else "FAIL")
    rv_counts, rv_exposure, rv_errors = _relative_value_diagnostics(observations, family_id) if family_id in RELATIVE_VALUE_FAMILIES else ({}, {}, [])
    if family_id in RELATIVE_VALUE_FAMILIES:
        legs = "PASS" if rv_counts["long_positive_assets"] >= 8 and rv_counts["short_positive_assets"] >= 8 else ("FAIL" if rv_counts["long_positive_assets"] + len(registered_assets) - rv_counts["long_positive_assets"] < 8 or rv_counts["short_positive_assets"] + len(registered_assets) - rv_counts["short_positive_assets"] < 8 else "INCONCLUSIVE")
        exposure_gate = "BLOCKED" if rv_errors else ("PASS" if rv_exposure["observed_boundaries"] else "INCONCLUSIVE")
    else: legs = "PASS"; exposure_gate = "PASS"
    integrity_errors.extend(rv_errors); integrity_gate = "BLOCKED" if integrity_errors else "PASS"
    gates = {"integrity": integrity_gate, "temporal": temporal, "asset_breadth": asset_breadth, "concentration": concentration, "neighbourhood": neighbourhood, "cost_survival": cost, "relative_value_legs": legs, "relative_value_exposure": exposure_gate}
    final = "BLOCKED" if integrity_gate == "BLOCKED" or cost == "BLOCKED" or exposure_gate == "BLOCKED" else ("FAIL" if any(g == "FAIL" for k, g in gates.items() if k != "integrity") else ("INCONCLUSIVE" if any(g == "INCONCLUSIVE" for k, g in gates.items() if k != "integrity") else "PASS"))
    receipt = {"contract_id": CONTRACT_ID, "contract_digest": CONTRACT_DIGEST, "registered_screen_id": SCREEN_ID, "input_universe_sha256": INPUT_UNIVERSE_SHA256, "family_id": family_id, "registered_variant_ids": list(variants), "adjacency_map": [list(p) for p in ADJACENCY[family_id]], "registered_asset_denominator": len(registered_assets), "registered_period_denominator": len(registered_periods), "usable_observation_counts": len(normalized), "blocked_observation_counts": len(expected_inputs) - len(normalized), "window_scores": window_scores, "window_statuses": stress_windows, "pooled_asset_scores": pooled, "positive_asset_count": sum(v["status"] == "POSITIVE_ASSET" for v in pooled.values()), "inconclusive_asset_count": sum(v["status"] == "INCONCLUSIVE_ASSET" for v in pooled.values()), "aggregate_stress_excess": _mean(aggregate_values), "positive_support_total": positive_total, "max_positive_asset_share": max_share, "variant_stress_scores": variant_scores, "qualifying_adjacent_pairs": qualifying, "baseline_advantage": baseline, "stress_advantage": stressed, "cost_retention_ratio": ratio, "turnover_diagnostics": {"turnover": "DESCRIPTIVE_ONLY", "trade_count": "DESCRIPTIVE_ONLY", "cost_delta": "STRESS_MINUS_BASELINE"}, "relative_value_leg_counts": rv_counts, "relative_value_exposure_integrity": rv_exposure if family_id in RELATIVE_VALUE_FAMILIES else None, "gate_results": gates, "final_status": final, "reason_codes": sorted(set(integrity_errors + normalization_errors))}
    return json.loads(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    return _sha(receipt)
