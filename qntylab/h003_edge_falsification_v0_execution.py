from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from . import h003_edge_falsification_v0 as h003
from . import strategy_test
from .data import load

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (17011, 17029, 17041, 17053, 17077, 17093, 17107, 17123, 17137, 17159)
REPORTING_RANGES = {
    "BLOCK_2022": ("2022-01-01T00:00:00Z", "2022-12-31T23:00:00Z"),
    "BLOCK_2023_KNOWN_HOLDOUT": ("2023-01-01T00:00:00Z", "2023-12-31T23:00:00Z"),
    "BLOCK_2024": ("2024-01-01T00:00:00Z", "2024-12-31T23:00:00Z"),
    "BLOCK_2025": ("2025-01-01T00:00:00Z", "2025-12-31T23:00:00Z"),
    "BLOCK_2026_TO_FREEZE": ("2026-01-01T00:00:00Z", "2026-09-08T20:00:00Z"),
}


def run_name(index: int, row: dict[str, Any]) -> str:
    return f"{index:02d}__{row['window_id']}__{row['cost_mode']}__{row['trial_id']}"


def block_id(window_id: str) -> str:
    return "BLOCK_2021" if window_id.startswith("BLOCK_2021_SEGMENT_") else window_id


def reporting_range(row: dict[str, Any]) -> tuple[str, str]:
    window_id = row["window_id"]
    if window_id.startswith("BLOCK_2021_SEGMENT_"):
        return row["config"]["evaluation_start"], row["config"]["evaluation_end"]
    try:
        return REPORTING_RANGES[window_id]
    except KeyError as exc:
        raise ValueError(f"unknown H003 V0 window: {window_id}") from exc


def _config_path(plan_dir: Path, trial_id: str) -> Path:
    matches = list((plan_dir / "configs").glob(f"*__{trial_id}.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one frozen config for {trial_id}, found {len(matches)}")
    return matches[0]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_one_receipt(run_dir: Path, row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_path = run_dir / "run_receipt.json"
    metrics_path = run_dir / "metrics.json"
    if not receipt_path.is_file() or not metrics_path.is_file():
        raise FileNotFoundError(f"missing frozen H003 run artifacts: {run_dir}")
    receipt = _read_json(receipt_path)
    metrics = _read_json(metrics_path)
    config = row["config"]
    checks = {
        "trial_id": row["trial_id"],
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "variant_id": "variant_00eb140f03a5f6ab40600160",
        "strategy_id": "H003_moving_average",
        "research_intent": "FOLLOW_UP",
        "input_sha256": row["input_sha256"],
        "gap_policy": "REJECT",
        "expected_interval": "1h",
    }
    for key, expected in checks.items():
        if receipt.get(key) != expected:
            raise RuntimeError(f"H003 receipt {key} mismatch for {row['trial_id']}")
    if receipt.get("status") != "completed":
        raise RuntimeError(f"H003 receipt not completed: {row['trial_id']}")
    if receipt.get("evaluation_range") != {"start": config["evaluation_start"], "end": config["evaluation_end"]}:
        raise RuntimeError(f"H003 receipt evaluation window mismatch: {row['trial_id']}")
    if receipt.get("fee_assumption") != {"fee_bps": config["fee_bps"]} or receipt.get("slippage_assumption") != {"slippage_bps": config["slippage_bps"]}:
        raise RuntimeError(f"H003 receipt cost mismatch: {row['trial_id']}")
    if receipt.get("result_artifact_sha256", {}).get("metrics") != strategy_test.sha256_path(metrics_path):
        raise RuntimeError(f"H003 metrics hash mismatch: {row['trial_id']}")
    if row["window_id"] == "BLOCK_2023_KNOWN_HOLDOUT":
        provenance = receipt.get("normalization_provenance")
        if provenance != h003.normalization_provenance_2023():
            raise RuntimeError("2023 H003 normalization provenance mismatch")
    return receipt, metrics


def verify_complete_receipts(workspace: Path) -> dict[str, dict[str, Any]]:
    plan = h003.compile_plan()
    runs = workspace / "runs"
    verified: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(plan, 1):
        run_dir = runs / run_name(index, row)
        receipt, metrics = _verify_one_receipt(run_dir, row)
        verified[row["trial_id"]] = {"receipt": receipt, "metrics": metrics, "run_dir": str(run_dir)}
    if set(verified) != {row["trial_id"] for row in plan} or len(verified) != 44:
        raise RuntimeError("H003 V0 receipt set is not exactly the frozen 44-trial matrix")
    return verified


def execute_frozen_plan(workspace: Path, *, research_root: Path | None = None) -> dict[str, Any]:
    """Execute only the already-frozen 44-trial matrix, resumably and fail-closed.

    This function is frozen in the result-blind implementation PR but must not be
    called until that PR is reviewed and merged.
    """
    plan_dir = workspace / "plan"
    if not plan_dir.exists():
        h003.write_plan(plan_dir)
    plan = h003.compile_plan()
    runs = workspace / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    executed: list[str] = []
    skipped: list[str] = []
    for index, row in enumerate(plan, 1):
        run_dir = runs / run_name(index, row)
        if run_dir.exists():
            _verify_one_receipt(run_dir, row)
            skipped.append(row["trial_id"])
            continue
        config_path = _config_path(plan_dir, row["trial_id"])
        config = _read_json(config_path)
        input_path = ROOT / config["input_path"]
        if not input_path.is_file():
            raise FileNotFoundError(f"missing frozen H003 input: {input_path}")
        if strategy_test.sha256_path(input_path) != row["input_sha256"]:
            raise RuntimeError(f"frozen H003 input SHA mismatch for {row['window_id']}")
        kwargs: dict[str, Any] = {}
        if research_root is not None:
            kwargs["research_root"] = research_root
        result = strategy_test.run_strategy(
            strategy_id="H003_moving_average",
            input_path=input_path,
            config_path=config_path,
            output=run_dir,
            command=["H003_EDGE_FALSIFICATION_V0", row["window_id"], row["cost_mode"], row["trial_id"]],
            **kwargs,
        )
        if result["receipt"].get("trial_id") != row["trial_id"]:
            raise RuntimeError("strategy_test returned a trial outside the frozen H003 authorization")
        executed.append(row["trial_id"])
    verified = verify_complete_receipts(workspace)
    receipt = {
        "schema_version": "1.0.0",
        "authorization_id": "H003_EDGE_FALSIFICATION_V0",
        "trial_count": 44,
        "executed_trial_ids": executed,
        "resumed_verified_trial_ids": skipped,
        "complete_trial_ids": sorted(verified),
    }
    out = workspace / "execution_receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def block_shuffled_timing(held: np.ndarray, seed: int, block_size: int = 168) -> np.ndarray:
    held = np.asarray(held, dtype=float)
    if len(held) == 0 or not np.all(np.isin(held, [0.0, 1.0])):
        raise ValueError("binary held-position path required")
    full = len(held) // block_size
    cut = full * block_size
    blocks = [held[i * block_size : (i + 1) * block_size].copy() for i in range(full)]
    rng = np.random.Generator(np.random.PCG64(seed))
    order = rng.permutation(full) if full else np.array([], dtype=int)
    head = np.concatenate([blocks[int(i)] for i in order]) if full else np.array([], dtype=float)
    return np.concatenate([head, held[cut:].copy()])


def _control_returns(market_returns: np.ndarray, held: np.ndarray, total_cost_bps: float) -> np.ndarray:
    market_returns = np.asarray(market_returns, dtype=float)
    held = np.asarray(held, dtype=float)
    if len(market_returns) != len(held):
        raise ValueError("control held path must match market-return path")
    # Conservative boundary convention: transitions within the reporting path are
    # charged; no invented exit is charged after the final owned return.
    changes = np.r_[np.abs(np.diff(held)), 0.0]
    return held * market_returns - changes * float(total_cost_bps) / 10_000.0


def _window_data(row: dict[str, Any]) -> tuple[list[str], np.ndarray, np.ndarray]:
    config = row["config"]
    path = ROOT / config["input_path"]
    if strategy_test.sha256_path(path) != row["input_sha256"]:
        raise RuntimeError(f"analysis input SHA mismatch: {row['window_id']}")
    rows = load(path)
    selected = [item for item in rows if config["evaluation_start"] <= item["timestamp"] <= config["evaluation_end"]]
    if len(selected) < 3 or selected[0]["timestamp"] != config["evaluation_start"] or selected[-1]["timestamp"] != config["evaluation_end"]:
        raise RuntimeError(f"analysis window incomplete: {row['window_id']}")
    strategy_test._reject_timestamp_gaps(selected, "1h")
    timestamps = [item["timestamp"] for item in selected]
    close = np.asarray([float(item["close"]) for item in selected], dtype=float)
    position = h003.reconstruct_h003(close)
    return timestamps, close, position


def _median_finite(values: list[float | None]) -> float | None:
    if not values or any(value is None or not np.isfinite(float(value)) for value in values):
        return None
    return float(np.median(np.asarray(values, dtype=float)))


def _prior_2023_failure_preserved() -> bool:
    decisions_path = ROOT / "experiments/research/decisions.jsonl"
    for line in decisions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event_id") == "event_3206c7b09c089b274ca027a5":
            return (
                event.get("status") == "GRAVEYARDED"
                and event.get("scope") == "EXACT_VARIANT"
                and event.get("reason_codes") == ["FAILED_2023_HOLDOUT_MULTIPLE_GATES"]
            )
    return False


def analyze_frozen_results(workspace: Path) -> dict[str, Any]:
    verified = verify_complete_receipts(workspace)
    plan = h003.compile_plan()
    segments: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in plan:
        timestamps, close, position = _window_data(row)
        cost_bps = float(row["config"]["fee_bps"]) + float(row["config"]["slippage_bps"])
        official = strategy_test._metrics(close, position, cost_bps)
        stored = verified[row["trial_id"]]["metrics"]
        if official != stored:
            raise RuntimeError(f"analysis does not reproduce strategy_test metrics: {row['trial_id']}")
        all_net = h003.net_return_path(close, position, cost_bps)
        market = close[1:] / close[:-1] - 1.0
        report_start, report_end = reporting_range(row)
        mask = h003.owned_return_mask(timestamps, report_start, report_end)
        held = position[:-1][mask]
        item = {
            "window_id": row["window_id"],
            "net": all_net[mask],
            "market": market[mask],
            "held": held,
            "cost_bps": cost_bps,
        }
        segments.setdefault(block_id(row["window_id"]), {}).setdefault(row["cost_mode"], []).append(item)

    complete_by_cost: dict[str, list[np.ndarray]] = {name: [] for name in ("zero_cost_diagnostic", "baseline", "stress", "severe_stress")}
    complete_market: list[np.ndarray] = []
    block_rows: dict[str, Any] = {}
    random_wins_sharpe = 0
    random_wins_calmar = 0
    for block in ("BLOCK_2021", "BLOCK_2022", "BLOCK_2023_KNOWN_HOLDOUT", "BLOCK_2024", "BLOCK_2025", "BLOCK_2026_TO_FREEZE"):
        modes = segments.get(block)
        if modes is None or any(mode not in modes for mode in complete_by_cost):
            raise RuntimeError(f"incomplete H003 analysis block: {block}")
        block_metrics: dict[str, Any] = {}
        for mode in complete_by_cost:
            path = np.concatenate([segment["net"] for segment in modes[mode]])
            block_metrics[mode] = h003.metrics_from_returns(path)
            complete_by_cost[mode].append(path)
        market_parts = [segment["market"] for segment in modes["baseline"]]
        market_path = np.concatenate(market_parts)
        buyhold = h003.metrics_from_returns(market_path)
        complete_market.append(market_path)

        random_metrics = []
        shuffle_metrics = []
        delayed_metrics = []
        for seed in SEEDS:
            random_parts = []
            shuffle_parts = []
            for segment in modes["baseline"]:
                random_held = h003.exposure_matched_random_timing(segment["held"], seed)
                shuffled_held = block_shuffled_timing(segment["held"], seed)
                random_parts.append(_control_returns(segment["market"], random_held, segment["cost_bps"]))
                shuffle_parts.append(_control_returns(segment["market"], shuffled_held, segment["cost_bps"]))
            random_metrics.append(h003.metrics_from_returns(np.concatenate(random_parts)))
            shuffle_metrics.append(h003.metrics_from_returns(np.concatenate(shuffle_parts)))
        for segment in modes["baseline"]:
            delayed_metrics.append(_control_returns(segment["market"], h003.delayed_24h(segment["held"]), segment["cost_bps"]))
        delayed = h003.metrics_from_returns(np.concatenate(delayed_metrics))
        random_median_sharpe = _median_finite([item["annualized_sharpe"] for item in random_metrics])
        random_median_calmar = _median_finite([item["calmar_ratio"] for item in random_metrics])
        shuffle_median_sharpe = _median_finite([item["annualized_sharpe"] for item in shuffle_metrics])
        shuffle_median_calmar = _median_finite([item["calmar_ratio"] for item in shuffle_metrics])
        base = block_metrics["baseline"]
        if random_median_sharpe is not None and base["annualized_sharpe"] is not None and base["annualized_sharpe"] > random_median_sharpe:
            random_wins_sharpe += 1
        if random_median_calmar is not None and base["calmar_ratio"] is not None and base["calmar_ratio"] > random_median_calmar:
            random_wins_calmar += 1
        block_rows[block] = {
            "h003": block_metrics,
            "buy_and_hold": buyhold,
            "exposure_matched_random_median": {"annualized_sharpe": random_median_sharpe, "calmar_ratio": random_median_calmar},
            "block_shuffled_diagnostic_median": {"annualized_sharpe": shuffle_median_sharpe, "calmar_ratio": shuffle_median_calmar},
            "delayed_24h_diagnostic": delayed,
        }

    full = {mode: h003.metrics_from_returns(np.concatenate(parts)) for mode, parts in complete_by_cost.items()}
    buyhold_full = h003.metrics_from_returns(np.concatenate(complete_market))
    prior_preserved = _prior_2023_failure_preserved()
    summary = {
        "baseline": full["baseline"],
        "stress": full["stress"],
        "buy_and_hold": buyhold_full,
        "block_random_wins_sharpe": random_wins_sharpe,
        "block_random_wins_calmar": random_wins_calmar,
        "prior_2023_failure_preserved": prior_preserved,
    }
    result = {
        "schema_version": "1.0.0",
        "authorization_id": "H003_EDGE_FALSIFICATION_V0",
        "trial_count": 44,
        "prior_2023_failure_preserved": prior_preserved,
        "complete_sample": {**full, "buy_and_hold": buyhold_full},
        "blocks": block_rows,
        "decision_summary": summary,
        "verdict": h003.verdict(summary),
    }
    output = workspace / "analysis.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return result
