"""Read-only input materialization for the frozen Sprint-v2 experiment.

This module deliberately stops before ranking, weighting, returns, IC, or any
other outcome computation.  It accepts only the committed local freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .cross_section import factor_scores
from .data import load_funding, load_perp, load_perp_daily, sha256

DATASET_ROOT_SHA256 = "20baddd5ff1abe36e3d4ce02f352028c2a95afdb59904db077514912473c15a5"
UNION_SHA256 = "cb75d98621f72e12beaed1ce41cb15d6ffad01e8be66eaf3ae07517e12c60153"
LEDGER_SHA256 = "d41cf6b15357d64b91709a9ccc9973da89a9fe9a93cc34388c58ba50fbec8e1d"
INVENTORY_SHA256 = "d662ebdfcdc75d745927f3434c70722a5ba65007f65385b883c44e19c2fd53da"
CUTOFF = "2026-06-30"
EXPECTED_FACTORS = (("H012_momentum_7d", 7, 1), ("H012_momentum_30d", 30, 1), ("H012_momentum_90d", 90, 1), ("H013_reversal_1d", 1, -1), ("H013_reversal_3d", 3, -1), ("H014_funding_24h", 1, -1), ("H014_funding_7d", 7, -1), ("H015_premium", 1, -1))


@dataclass(frozen=True)
class FrozenInputs:
    dates: tuple[str, ...]
    symbols: tuple[str, ...]
    close: np.ndarray
    funding: np.ndarray
    premium: np.ndarray
    eligible: np.ndarray
    funding_events: dict[str, tuple[dict[str, str], ...]]
    scores: dict[str, np.ndarray]
    cost_bps: tuple[int, ...]
    null_seed: int
    null_count: int
    null_same_universe_and_bucket_counts: bool


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_freeze(root: Path) -> tuple[dict, dict, list[dict]]:
    manifest = _read_json(root / "experiments/data/sprint_v2_pre_outcome_dataset_manifest.json")
    if not isinstance(manifest, dict): raise ValueError("dataset manifest must be an object")
    bound_root = manifest.pop("dataset_root_sha256", None)
    if bound_root != DATASET_ROOT_SHA256 or hashlib.sha256(_canonical(manifest)).hexdigest() != bound_root:
        raise ValueError("frozen dataset root verification failed")
    union = _read_json(root / "experiments/data/sprint_v2_union_selected.json")
    if not isinstance(union, dict): raise ValueError("union must be an object")
    union_core = {key: value for key, value in union.items() if key != "union_selected_sha256"}
    if union.get("union_selected_sha256") != UNION_SHA256 or hashlib.sha256(_canonical(union_core)).hexdigest() != UNION_SHA256:
        raise ValueError("frozen union verification failed")
    ledger_path = root / "data/archive/sprint_v2_universe_ledger.json"
    if sha256(ledger_path) != LEDGER_SHA256 or union.get("universe_ledger_sha256") != LEDGER_SHA256:
        raise ValueError("frozen universe ledger verification failed")
    if sha256(root / "data/archive/sprint_v2_1d_inventory.json") != INVENTORY_SHA256:
        raise ValueError("frozen daily inventory verification failed")
    ledger = _read_json(ledger_path)
    if not isinstance(ledger, list): raise ValueError("universe ledger must be a list")
    symbols = [item["symbol"] for item in union["symbols"]]
    if len(symbols) != 181 or len(set(symbols)) != 181 or manifest["universe"]["union_count"] != 181:
        raise ValueError("frozen union membership invalid")
    for row in manifest["auxiliary_coverage"]:
        for kind, suffix in (("funding", "-funding.csv"), ("premium", "-perp-1h.csv")):
            source = row[kind]
            raw = root / "data/raw" / f"{row['symbol']}{suffix}"
            if source["state"] == "VALID":
                if not raw.exists() or sha256(raw) != source["sha256"]: raise ValueError(f"frozen {kind} source hash mismatch: {row['symbol']}")
            elif source["state"] != "NO_SOURCE_DATA": raise ValueError(f"invalid {kind} source state")
    for symbol in symbols:
        raw = root / "data/raw" / f"{symbol}-perp-1d.csv"; receipt = root / "data/archive/panels" / f"{symbol}.json"
        if not raw.exists() or not receipt.exists() or sha256(raw) != _read_json(receipt)["panel_sha256"]:
            raise ValueError(f"frozen daily source hash mismatch: {symbol}")
    return manifest, union, ledger


def _daily_funding(rows: list[dict[str, str]], dates: dict[str, int]) -> np.ndarray:
    values = np.full(len(dates), np.nan)
    grouped: dict[str, float] = {}
    for row in rows:
        day = row["timestamp"][:10]
        if day in dates: grouped[day] = grouped.get(day, 0.0) + float(row["funding_rate"])
    for day, value in grouped.items(): values[dates[day]] = value
    return values


def _daily_premium(rows: list[dict[str, str]], dates: dict[str, int]) -> np.ndarray:
    values = np.full(len(dates), np.nan); latest: dict[str, tuple[str, float]] = {}
    for row in rows:
        day, stamp = row["timestamp"][:10], row["timestamp"]
        if day in dates and (day not in latest or stamp > latest[day][0]): latest[day] = (stamp, float(row["premium"]))
    for day, (_, value) in latest.items(): values[dates[day]] = value
    return values


def materialize(root: Path) -> FrozenInputs:
    """Verify and load inputs only; this function cannot evaluate an outcome."""
    manifest, union, ledger = _verify_freeze(root)
    spec = _read_json(root / "experiments/specs/sprint_v2_cross_sectional.json")
    if not isinstance(spec, dict) or spec.get("sprint") != "v2_cross_sectional" or manifest.get("sample_cutoff") != CUTOFF:
        raise ValueError("frozen experiment specification mismatch")
    if tuple((factor["id"], factor["lookback_days"], factor["direction"]) for factor in spec["factors"]) != EXPECTED_FACTORS or spec["portfolio"].get("costs_bps") != [5, 10, 20] or spec["null"] != {"count": 100, "seed": 20260728, "same_universe_and_bucket_counts": True, "report_zero_cost_and_costed": True}:
        raise ValueError("frozen factor or execution configuration mismatch")
    dates = tuple(row["date"] for row in ledger if row["date"] <= CUTOFF)
    if len(dates) != len(set(dates)) or dates != tuple(sorted(dates)): raise ValueError("invalid frozen daily ledger dates")
    symbols = tuple(item["symbol"] for item in union["symbols"]); index = {symbol: j for j, symbol in enumerate(symbols)}; day_index = {day: i for i, day in enumerate(dates)}
    shape = (len(dates), len(symbols)); close = np.full(shape, np.nan); funding = np.full(shape, np.nan); premium = np.full(shape, np.nan); eligible = np.zeros(shape, dtype=bool); funding_events: dict[str, tuple[dict[str, str], ...]] = {}
    coverage = {row["symbol"]: row for row in manifest["auxiliary_coverage"]}
    for j, symbol in enumerate(symbols):
        for row in load_perp_daily(root / "data/raw" / f"{symbol}-perp-1d.csv"):
            day = row["timestamp"][:10]
            if day in day_index: close[day_index[day], j] = float(row["close"])
        source = coverage[symbol]
        if source["funding"]["state"] == "VALID":
            events = load_funding(root / "data/raw" / f"{symbol}-funding.csv")
            funding[:, j] = _daily_funding(events, day_index)
            funding_events[symbol] = tuple(event for event in events if event["timestamp"][:10] in day_index)
        if source["premium"]["state"] == "VALID": premium[:, j] = _daily_premium(load_perp(root / "data/raw" / f"{symbol}-perp-1h.csv"), day_index)
    for t, row in enumerate(ledger):
        for symbol in row["selected_symbols"]:
            if symbol in index: eligible[t, index[symbol]] = True
    scores = {factor["id"]: factor_scores(close, funding if factor["id"].startswith("H014") else None, premium if factor["id"] == "H015_premium" else None, factor["id"], factor["lookback_days"]) for factor in spec["factors"]}
    return FrozenInputs(dates, symbols, close, funding, premium, eligible, funding_events, scores, tuple(spec["portfolio"]["costs_bps"]), spec["null"]["seed"], spec["null"]["count"], spec["null"]["same_universe_and_bucket_counts"])


def structural_report(inputs: FrozenInputs) -> dict:
    """Return only identity, dimensional, availability, and breadth facts."""
    return {"dataset_root_verified": True, "union_count": len(inputs.symbols), "date_range": [inputs.dates[0], inputs.dates[-1]], "matrix_dimensions": list(inputs.close.shape), "missing_observations": {name: int((~np.isfinite(score)).sum()) for name, score in inputs.scores.items()}, "funding_coverage_counts": {"available": int(np.isfinite(inputs.funding).sum()), "missing": int((~np.isfinite(inputs.funding)).sum())}, "premium_coverage_counts": {"available": int(np.isfinite(inputs.premium).sum()), "missing": int((~np.isfinite(inputs.premium)).sum())}, "breadth_counts": {"minimum": int(inputs.eligible.sum(axis=1).min()), "maximum": int(inputs.eligible.sum(axis=1).max())}, "cost_bps": list(inputs.cost_bps), "random_rank_null": {"seed": inputs.null_seed, "count": inputs.null_count, "same_universe_and_bucket_counts": inputs.null_same_universe_and_bucket_counts}}


def main() -> None:
    parser = argparse.ArgumentParser(description="verify and materialize frozen Sprint-v2 inputs only")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(); print(json.dumps(structural_report(materialize(args.root)), sort_keys=True))


if __name__ == "__main__": main()
