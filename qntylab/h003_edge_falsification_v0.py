from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from . import research_ledger
from .strategies import positions

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_PATH = ROOT / "experiments/specs/h003_edge_falsification_v0_trial_authorization.json"
ANALYSIS_CONTRACT_PATH = ROOT / "experiments/specs/h003_edge_falsification_v0_analysis_contract.json"
PREREG_PATH = ROOT / "experiments/specs/h003_edge_falsification_v0.json"
RAW_INPUT = "data/raw/SOLUSDT-1h.csv"
NORMALIZED_2023_INPUT = "data/derived/focused_trend_validation_v1/SOLUSDT-spot-1h-2023-halt-normalized.csv"
NORMALIZED_2023_MANIFEST = "data/derived/focused_trend_validation_v1/SOLUSDT-spot-1h-2023-halt-normalized.manifest.json"
SOURCE_RESOLUTION_PATH = "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.json"
SOURCE_RESOLUTION_SHA = "a945478ce34aec6d4e44c57e407b1a14027b4e9b99b788f9fd08c435804e54b6"
SOURCE_RESOLUTION_COMMIT = "5a0fe6baae1d3ec9762384e192adb9b20e472263"
RAW_SNAPSHOT_MANIFEST_PATH = "data/manifests/SOLUSDT-1h.json"
RAW_SNAPSHOT_MANIFEST_COMMIT = "7c3c1b4a9d08625cd973bba2747a1a3de740bdf7"
RAW_SNAPSHOT_SHA = "c431aa068acbfedf3cb0c38845dfac275044a9cf83367075b47d47f06974e99d"
NORMALIZED_SHA = "62cee85e0a0f7b903fadc77a8f275e774f0ff3ecfff9fba9ea51a535376f70f1"
NORMALIZED_MANIFEST_SHA = "232b42f1d9d968faedc4fe86018cbc5767261af901391bb7e189fd1aa1a6e5af"
ANNUAL_BARS = 365 * 24


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def normalization_provenance_2023() -> dict[str, Any]:
    return {
        "normalization_id": "PREREGISTER_BINANCE_SPOT_HALT_NORMALIZATION_V1",
        "normalization_version": "BINANCE_SPOT_HALT_NORMALIZATION_V1",
        "reason_code": "BINANCE_SPOT_AUTHORITATIVE_NO_TRADE_HALT",
        "derived_input_path": NORMALIZED_2023_INPUT,
        "derived_input_sha256": NORMALIZED_SHA,
        "derived_manifest_path": NORMALIZED_2023_MANIFEST,
        "derived_manifest_sha256": NORMALIZED_MANIFEST_SHA,
        "source_resolution_artifact_path": SOURCE_RESOLUTION_PATH,
        "source_resolution_artifact_sha256": SOURCE_RESOLUTION_SHA,
        "authoritative_raw_path": RAW_INPUT,
        "authoritative_raw_sha256": RAW_SNAPSHOT_SHA,
        "normalized_timestamp": "2023-03-24T13:00:00Z",
        "source_resolution_git_commit": SOURCE_RESOLUTION_COMMIT,
        "authoritative_raw_snapshot_manifest_path": RAW_SNAPSHOT_MANIFEST_PATH,
        "authoritative_raw_snapshot_manifest_git_commit": RAW_SNAPSHOT_MANIFEST_COMMIT,
    }


def _base_config(window: dict[str, Any], cost: dict[str, Any]) -> dict[str, Any]:
    is_2023 = window["id"] == "BLOCK_2023_KNOWN_HOLDOUT"
    config: dict[str, Any] = {
        "schema_version": 1,
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "input_path": NORMALIZED_2023_INPUT if is_2023 else RAW_INPUT,
        "evaluation_start": window["evaluation_start"],
        "evaluation_end": window["evaluation_end"],
        "initial_capital": 10000.0,
        "fee_bps": float(cost["fee_bps"]),
        "slippage_bps": float(cost["slippage_bps"]),
        "funding_boundary_mode": "NOT_APPLICABLE",
        "gap_policy": "REJECT",
        "expected_interval": "1h",
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "research_intent": "FOLLOW_UP",
        "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
    }
    if is_2023:
        config["normalization_provenance"] = normalization_provenance_2023()
    return config


def compile_plan() -> list[dict[str, Any]]:
    authorization = _load(AUTHORIZATION_PATH)
    metadata = authorization["metadata"]
    expected_ids = set(authorization["authorized_trial_ids"])
    rows: list[dict[str, Any]] = []
    for window in metadata["windows"]:
        for cost in metadata["cost_modes"]:
            config = _base_config(window, cost)
            trial_id = research_ledger.compute_trial_id(
                variant_id=authorization["variant_id"],
                symbol=metadata["symbol"],
                input_sha256=window["input_sha256"],
                evaluation_start=config["evaluation_start"],
                evaluation_end=config["evaluation_end"],
                fee_bps=config["fee_bps"],
                slippage_bps=config["slippage_bps"],
                gap_policy=config["gap_policy"],
                expected_interval=config["expected_interval"],
            )
            rows.append({
                "window_id": window["id"],
                "cost_mode": cost["id"],
                "input_sha256": window["input_sha256"],
                "trial_id": trial_id,
                "config": config,
            })
    actual_ids = [row["trial_id"] for row in rows]
    if len(rows) != 44 or len(set(actual_ids)) != 44 or set(actual_ids) != expected_ids:
        raise RuntimeError("compiled H003 V0 plan does not exactly match frozen 44-trial authorization")
    return rows


def write_plan(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    rows = compile_plan()
    configs = output_dir / "configs"
    configs.mkdir()
    manifest_rows = []
    for index, row in enumerate(rows, 1):
        filename = f"{index:02d}__{row['window_id']}__{row['cost_mode']}__{row['trial_id']}.json"
        path = configs / filename
        path.write_text(json.dumps(row["config"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_rows.append({key: row[key] for key in ("window_id", "cost_mode", "input_sha256", "trial_id")} | {"config_path": str(path)})
    manifest = output_dir / "plan.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.0.0",
        "authorization_id": "H003_EDGE_FALSIFICATION_V0",
        "result_blind": True,
        "execution_performed": False,
        "trial_count": len(rows),
        "trials": manifest_rows,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def net_return_path(close: np.ndarray, position: np.ndarray, total_cost_bps: float) -> np.ndarray:
    close = np.asarray(close, dtype=float)
    position = np.asarray(position, dtype=float)
    if len(close) != len(position) or len(close) < 3:
        raise ValueError("matching close/position series of at least 3 required")
    returns = close[1:] / close[:-1] - 1.0
    held = position[:-1]
    changes = np.abs(np.diff(position))
    return held * returns - changes * float(total_cost_bps) / 10_000.0


def metrics_from_returns(net: np.ndarray) -> dict[str, float | int | None]:
    net = np.asarray(net, dtype=float)
    if len(net) < 2 or not np.all(np.isfinite(net)):
        raise ValueError("finite return path with at least two observations required")
    equity = np.cumprod(1.0 + net)
    peak = np.maximum.accumulate(np.r_[1.0, equity])[1:]
    maximum_drawdown = float(np.min(equity / peak - 1.0))
    mean = float(net.mean())
    std = float(net.std(ddof=0))
    net_total = float(equity[-1] - 1.0)
    years = len(net) / ANNUAL_BARS
    annualized_return = None
    if 1.0 + net_total > 0 and years > 0:
        exponent = math.log1p(net_total) / years
        if exponent < 700:
            annualized_return = float(math.expm1(exponent))
    sharpe = float(mean / std * math.sqrt(ANNUAL_BARS)) if std else None
    calmar = None if annualized_return is None or maximum_drawdown == 0 else float(annualized_return / abs(maximum_drawdown))
    return {
        "observation_count": int(len(net)),
        "net_return": net_total,
        "annualized_return": annualized_return,
        "annualized_sharpe": sharpe,
        "maximum_drawdown": maximum_drawdown,
        "calmar_ratio": calmar,
    }


def reconstruct_h003(close: np.ndarray) -> np.ndarray:
    return positions("H003_moving_average", np.asarray(close, dtype=float), {"fast": 48, "slow": 192, "mode": "long_flat"})


def owned_return_mask(timestamps: list[str], reporting_start: str, reporting_end: str) -> np.ndarray:
    if len(timestamps) < 3:
        raise ValueError("at least three timestamps required")
    ending = np.asarray(timestamps[1:], dtype=object)
    return (ending >= reporting_start) & (ending <= reporting_end)


def exposure_matched_random_timing(held: np.ndarray, seed: int) -> np.ndarray:
    held = np.asarray(held, dtype=float)
    if len(held) == 0 or not np.all(np.isin(held, [0.0, 1.0])):
        raise ValueError("binary held-position path required")
    states: list[int] = []
    lengths: list[int] = []
    start = 0
    for i in range(1, len(held) + 1):
        if i == len(held) or held[i] != held[start]:
            states.append(int(held[start]))
            lengths.append(i - start)
            start = i
    by_state = {0: [n for s, n in zip(states, lengths) if s == 0], 1: [n for s, n in zip(states, lengths) if s == 1]}
    rng = np.random.Generator(np.random.PCG64(seed))
    shuffled = {state: list(rng.permutation(values)) for state, values in by_state.items()}
    offsets = {0: 0, 1: 0}
    out: list[float] = []
    for state in states:
        length = shuffled[state][offsets[state]]
        offsets[state] += 1
        out.extend([float(state)] * int(length))
    result = np.asarray(out, dtype=float)
    if len(result) != len(held) or int(result.sum()) != int(held.sum()):
        raise RuntimeError("exposure-matched control invariant failed")
    return result


def delayed_24h(held: np.ndarray) -> np.ndarray:
    held = np.asarray(held, dtype=float)
    out = np.zeros_like(held)
    if len(held) > 24:
        out[24:] = held[:-24]
    return out


def verdict(summary: dict[str, Any]) -> str:
    required = ("baseline", "stress", "buy_and_hold", "block_random_wins_sharpe", "block_random_wins_calmar", "prior_2023_failure_preserved")
    if any(key not in summary for key in required):
        return "BLOCKED_BY_INPUT_OR_INTEGRITY"
    baseline, stress, buyhold = summary["baseline"], summary["stress"], summary["buy_and_hold"]
    required_metrics = (
        baseline.get("annualized_sharpe"), baseline.get("calmar_ratio"), baseline.get("maximum_drawdown"),
        stress.get("annualized_sharpe"), stress.get("calmar_ratio"), buyhold.get("annualized_sharpe"), buyhold.get("calmar_ratio"), buyhold.get("maximum_drawdown"),
    )
    if any(value is None or not math.isfinite(float(value)) for value in required_metrics):
        return "BLOCKED_BY_INPUT_OR_INTEGRITY"
    falsified = (
        baseline["annualized_sharpe"] <= buyhold["annualized_sharpe"]
        or baseline["calmar_ratio"] <= buyhold["calmar_ratio"]
        or stress["annualized_sharpe"] <= 0
        or stress["calmar_ratio"] <= 0
        or summary["block_random_wins_sharpe"] < 4
        or summary["block_random_wins_calmar"] < 4
    )
    if falsified:
        return "FALSIFIED"
    candidate = (
        baseline["maximum_drawdown"] > buyhold["maximum_drawdown"]
        and summary["block_random_wins_sharpe"] >= 4
        and summary["block_random_wins_calmar"] >= 4
        and summary["prior_2023_failure_preserved"] is True
    )
    return "DEFENSIVE_EDGE_CANDIDATE" if candidate else "FRAGILE_OR_UNPROVEN"
