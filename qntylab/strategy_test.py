from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .backtest import evaluate
from .data import load
from .research_ledger import (
    RESEARCH_ROOT,
    RESEARCH_INTENTS,
    LedgerError,
    append_canonical_event,
    build_trial_completed_event,
    compute_variant_id,
    preflight,
)
from .strategies import positions

SCHEMA_VERSION = 1
STRATEGY_VERSION = "existing-qntylab-strategies-v1"
EXPLORATORY_ONLY = True
NOT_APPLICABLE = "NOT_APPLICABLE"
GAP_POLICY_REJECT = "REJECT"
EXPECTED_INTERVAL_1H = "1h"
RELEVANT_SOURCE_PATHS = (
    "qntylab/research_ledger.py",
    "qntylab/strategy_test.py",
    "qntylab/backtest.py",
    "qntylab/strategies.py",
    "qntylab/data.py",
)
BOUNDARY_MODES = {NOT_APPLICABLE, "STRICTLY_BEFORE_BAR_OPEN", "AT_OR_BEFORE_BAR_OPEN"}
STRATEGIES = {
    "H002_momentum": {"parameters": {"lookback": int, "mode": str}, "uses_funding": False},
    "H003_moving_average": {"parameters": {"fast": int, "slow": int, "mode": str}, "uses_funding": False},
    "H004_mean_reversion": {"parameters": {"lookback": int, "threshold": float, "mode": str}, "uses_funding": False},
    "H005_donchian": {"parameters": {"lookback": int, "mode": str}, "uses_funding": False},
    "H006_short_horizon_reversal": {"parameters": {"lookback": int, "mode": str}, "uses_funding": False},
    "H007_volatility_scaled_moving_average": {
        "parameters": {
            "fast": int,
            "slow": int,
            "realized_volatility_window": int,
            "volatility_baseline_window": int,
            "minimum_multiplier": float,
            "maximum_multiplier": float,
            "mode": str,
        },
        "uses_funding": False,
    },
}
CONFIG_KEYS = {
    "schema_version",
    "strategy_id",
    "strategy_version",
    "input_path",
    "evaluation_start",
    "evaluation_end",
    "initial_capital",
    "fee_bps",
    "slippage_bps",
    "funding_boundary_mode",
    "gap_policy",
    "expected_interval",
    "candidate_id",
    "research_intent",
    "parameters",
}
SUMMARY_FIELDS = (
    "run_id",
    "repository_commit",
    "relevant_source_sha256",
    "strategy_id",
    "symbol",
    "period",
    "cost_mode",
    "observation_count",
    "trade_count",
    "exposure_fraction",
    "gross_return",
    "net_return",
    "buy_and_hold_return",
    "excess_return_vs_buy_and_hold",
    "total_cost",
    "maximum_drawdown",
    "status",
    "receipt_path",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relevant_source_digests(repo_root: Path | None = None, paths: tuple[str, ...] = RELEVANT_SOURCE_PATHS) -> dict[str, str]:
    root = repo_root or Path.cwd()
    return {path: sha256_path(root / path) for path in sorted(paths)}


def relevant_source_sha256(repo_root: Path | None = None, paths: tuple[str, ...] = RELEVANT_SOURCE_PATHS) -> str:
    digest_rows = [{"path": path, "sha256": digest} for path, digest in relevant_source_digests(repo_root, paths).items()]
    return sha256_bytes(_canonical_bytes(digest_rows))


def relevant_source_dirty_paths(repo_root: Path | None = None, paths: tuple[str, ...] = RELEVANT_SOURCE_PATHS) -> list[str]:
    root = repo_root or Path.cwd()
    dirty: list[str] = []
    for path in sorted(paths):
        worktree = subprocess.run(["git", "diff", "--quiet", "--", path], cwd=root, stderr=subprocess.DEVNULL)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", path], cwd=root, stderr=subprocess.DEVNULL)
        if worktree.returncode or staged.returncode:
            dirty.append(path)
    return dirty


def relevant_source_clean(repo_root: Path | None = None, paths: tuple[str, ...] = RELEVANT_SOURCE_PATHS) -> bool:
    return not relevant_source_dirty_paths(repo_root, paths)


def assert_relevant_source_clean(repo_root: Path | None = None, paths: tuple[str, ...] = RELEVANT_SOURCE_PATHS) -> None:
    dirty = relevant_source_dirty_paths(repo_root, paths)
    if dirty:
        raise RuntimeError(f"relevant tracked source has uncommitted changes: {dirty}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid config JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("config must be a JSON object")
    return value


def _finite_number(config: dict[str, Any], key: str, *, minimum: float | None = None) -> float:
    value = config.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    return number


def _validate_parameters(strategy_id: str, params: dict[str, Any]) -> None:
    expected = STRATEGIES[strategy_id]["parameters"]
    if set(params) != set(expected):
        raise ValueError(f"{strategy_id} parameters must contain exactly {sorted(expected)}")
    for key, kind in expected.items():
        value = params[key]
        if kind is int:
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"parameters.{key} must be a positive integer")
        elif kind is float:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"parameters.{key} must be a positive finite number")
    mode = params.get("mode")
    if mode is not None and mode not in {"long_flat", "long_short"}:
        raise ValueError("parameters.mode must be long_flat or long_short")
    if strategy_id in {"H003_moving_average", "H007_volatility_scaled_moving_average"} and params["fast"] >= params["slow"]:
        raise ValueError("parameters.fast must be less than parameters.slow")
    if strategy_id == "H007_volatility_scaled_moving_average":
        if params["mode"] != "long_flat":
            raise ValueError("H007_volatility_scaled_moving_average mode must be long_flat")
        if float(params["minimum_multiplier"]) < 0 or float(params["maximum_multiplier"]) > 1:
            raise ValueError("H007 multipliers must be within [0, 1]")
        if float(params["minimum_multiplier"]) > float(params["maximum_multiplier"]):
            raise ValueError("minimum_multiplier must be <= maximum_multiplier")


def load_config(path: Path, *, input_path: Path | None = None, strategy_id: str | None = None) -> dict[str, Any]:
    config = _load_json(path)
    config.setdefault("gap_policy", GAP_POLICY_REJECT)
    config.setdefault("expected_interval", EXPECTED_INTERVAL_1H)
    extra = set(config) - CONFIG_KEYS
    missing = CONFIG_KEYS - set(config)
    if extra:
        raise ValueError(f"unknown config keys: {sorted(extra)}")
    if missing:
        raise ValueError(f"missing config keys: {sorted(missing)}")
    if config["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {config['schema_version']!r}")
    if not isinstance(config["strategy_id"], str) or config["strategy_id"] not in STRATEGIES:
        raise ValueError(f"unknown strategy: {config['strategy_id']!r}")
    if strategy_id is not None and strategy_id != config["strategy_id"]:
        raise ValueError("CLI strategy does not match config strategy_id")
    if config["strategy_version"] != STRATEGY_VERSION:
        raise ValueError(f"unsupported strategy_version: {config['strategy_version']!r}")
    if config["funding_boundary_mode"] not in BOUNDARY_MODES:
        raise ValueError(f"unknown funding_boundary_mode: {config['funding_boundary_mode']!r}")
    if not STRATEGIES[config["strategy_id"]]["uses_funding"] and config["funding_boundary_mode"] != NOT_APPLICABLE:
        raise ValueError(f"{config['strategy_id']} does not use funding; funding_boundary_mode must be {NOT_APPLICABLE}")
    if not isinstance(config["parameters"], dict):
        raise ValueError("parameters must be an object")
    _validate_parameters(config["strategy_id"], config["parameters"])
    if not isinstance(config["evaluation_start"], str) or not isinstance(config["evaluation_end"], str):
        raise ValueError("evaluation_start and evaluation_end must be strings")
    if config["evaluation_start"] > config["evaluation_end"]:
        raise ValueError("invalid date range: evaluation_start is after evaluation_end")
    _finite_number(config, "initial_capital", minimum=0.0)
    _finite_number(config, "fee_bps", minimum=0.0)
    _finite_number(config, "slippage_bps", minimum=0.0)
    if input_path is not None:
        config["input_path"] = str(input_path)
    if not isinstance(config["input_path"], str) or not config["input_path"]:
        raise ValueError("input_path must be a non-empty string")
    if config["gap_policy"] != GAP_POLICY_REJECT:
        raise ValueError(f"unsupported gap_policy: {config['gap_policy']!r}")
    if config["expected_interval"] != EXPECTED_INTERVAL_1H:
        raise ValueError(f"unsupported expected_interval: {config['expected_interval']!r}")
    if not isinstance(config["candidate_id"], str) or not config["candidate_id"].strip():
        raise ValueError("candidate_id must be a non-empty string")
    if config["research_intent"] not in RESEARCH_INTENTS:
        raise ValueError(f"unsupported research_intent: {config['research_intent']!r}")
    return config


def _normalize_input_path(path: Path, config_path: Path) -> Path:
    if path.is_absolute():
        return path
    candidate = (Path.cwd() / path).resolve()
    if candidate.exists():
        return candidate
    return (config_path.parent / path).resolve()


def _symbol_from_input(path: Path) -> str:
    name = path.name
    for suffix in ("-perp-1h.csv", "-1h.csv", "-perp-1d.csv"):
        if name.endswith(suffix):
            return name.removesuffix(suffix)
    return path.stem


def _run_labels(run_id: str) -> dict[str, str]:
    parts = run_id.split("__")
    if len(parts) == 4:
        return {"strategy_id": parts[0], "symbol": parts[1], "period": parts[2], "cost_mode": parts[3]}
    return {"period": "", "cost_mode": ""}


def _evaluation_window(rows: list[dict[str, str]], start: str, end: str) -> tuple[int, int]:
    stamps = [row["timestamp"] for row in rows]
    indices = [i for i, stamp in enumerate(stamps) if start <= stamp <= end]
    if len(indices) < 3:
        raise ValueError("invalid date range: fewer than 3 rows in evaluation window")
    if indices != list(range(indices[0], indices[-1] + 1)):
        raise ValueError("invalid date range: selected rows are not contiguous")
    return indices[0], indices[-1] + 1


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _reject_timestamp_gaps(rows: list[dict[str, str]], expected_interval: str) -> None:
    if expected_interval != EXPECTED_INTERVAL_1H:
        raise ValueError(f"unsupported expected_interval: {expected_interval!r}")
    expected_delta = timedelta(hours=1)
    previous: datetime | None = None
    for row in rows:
        current = _parse_timestamp(row["timestamp"])
        if previous is not None and current - previous != expected_delta:
            raise ValueError(f"timestamp gap rejected: {previous.isoformat()} -> {current.isoformat()} ({current - previous})")
        previous = current


def _strategy_warmup_bars(strategy_id: str, params: dict[str, Any]) -> int:
    if strategy_id == "H006_short_horizon_reversal":
        return int(params["lookback"]) + 1
    if strategy_id == "H007_volatility_scaled_moving_average":
        rv_window = int(params["realized_volatility_window"])
        baseline_window = int(params["volatility_baseline_window"])
        return max(int(params["slow"]), rv_window + baseline_window + 1)
    return 0


def _warmup_window(lo: int, strategy_id: str, params: dict[str, Any]) -> tuple[int, int]:
    required = _strategy_warmup_bars(strategy_id, params)
    if lo < required:
        raise ValueError(f"insufficient warmup observations: need {required}, got {lo}")
    return lo - required, required


def _metrics(close: np.ndarray, position: np.ndarray, total_cost_bps: float) -> dict[str, Any]:
    result = evaluate(close, position, total_cost_bps)
    buy_and_hold_return = float(close[-1] / close[0] - 1)
    net_return = result["net_cumulative_return"]
    metrics = {
        "observation_count": int(len(close) - 1),
        "trade_count": result["trade_count"],
        "exposure_fraction": float(np.abs(position).mean()),
        "gross_return": result["gross_cumulative_return"],
        "net_return": net_return,
        "buy_and_hold_return": buy_and_hold_return,
        "excess_return_vs_buy_and_hold": float(net_return - buy_and_hold_return),
        "total_cost": result["fee_cost"],
        "maximum_drawdown": result["max_drawdown"],
    }
    _canonical_bytes(metrics)
    return metrics


def _validate_positions(position: np.ndarray, strategy_id: str, params: dict[str, Any]) -> None:
    if not np.all(np.isfinite(position)):
        raise ValueError("non-finite position values")
    lower, upper = (-1.0, 1.0) if params.get("mode") == "long_short" else (0.0, 1.0)
    if np.any(position < lower) or np.any(position > upper):
        raise ValueError(f"positions must be finite and within [{lower}, {upper}] for {strategy_id}")


def sanity_warnings(metrics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    numeric = ("gross_return", "net_return", "total_cost", "maximum_drawdown")
    if any(not isinstance(metrics.get(key), (int, float)) or isinstance(metrics.get(key), bool) or not math.isfinite(float(metrics[key])) for key in numeric):
        warnings.append("non-finite metric")
    if metrics.get("trade_count") == 0:
        warnings.append("zero trades")
    if isinstance(metrics.get("trade_count"), int) and 0 < metrics["trade_count"] < 10:
        warnings.append("fewer than 10 trades")
    if isinstance(metrics.get("net_return"), (int, float)) and not isinstance(metrics.get("net_return"), bool) and math.isfinite(float(metrics["net_return"])) and abs(float(metrics["net_return"])) > 1:
        warnings.append("absolute net return above 100%")
    if isinstance(metrics.get("maximum_drawdown"), (int, float)) and not isinstance(metrics.get("maximum_drawdown"), bool) and math.isfinite(float(metrics["maximum_drawdown"])) and float(metrics["maximum_drawdown"]) < -0.8:
        warnings.append("maximum drawdown below -80%")
    if (
        isinstance(metrics.get("gross_return"), (int, float))
        and isinstance(metrics.get("net_return"), (int, float))
        and isinstance(metrics.get("total_cost"), (int, float))
        and math.isfinite(float(metrics["gross_return"]))
        and math.isfinite(float(metrics["net_return"]))
        and math.isfinite(float(metrics["total_cost"]))
        and float(metrics["total_cost"]) > 0
        and float(metrics["gross_return"]) < float(metrics["net_return"])
    ):
        warnings.append("gross return lower than net return when costs are positive")
    return warnings


def _validate_finite_metrics(metrics: dict[str, Any]) -> None:
    for key, value in metrics.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite metric: {key}")


def run_strategy(
    *,
    strategy_id: str,
    input_path: Path,
    config_path: Path,
    output: Path,
    overwrite: bool = False,
    command: list[str] | None = None,
    research_root: Path = RESEARCH_ROOT,
    require_clean_source: bool = True,
) -> dict[str, Any]:
    if strategy_id not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy_id!r}")
    if output.exists():
        if not overwrite:
            raise FileExistsError(f"output directory already exists: {output}")
        if not output.is_dir():
            raise FileExistsError(f"output path exists and is not a directory: {output}")
    if require_clean_source:
        assert_relevant_source_clean()
    source_sha256 = relevant_source_sha256()
    config = load_config(config_path, input_path=input_path, strategy_id=strategy_id)
    normalized_input = _normalize_input_path(Path(config["input_path"]), config_path)
    if not normalized_input.exists():
        raise FileNotFoundError(f"missing input: {normalized_input}")
    input_sha256 = sha256_path(normalized_input)
    symbol = _symbol_from_input(normalized_input)
    computed_variant_id = compute_variant_id(config)
    ledger_binding = preflight(config=config, symbol=symbol, input_sha256=input_sha256, root=research_root)
    if ledger_binding["variant_id"] != computed_variant_id:
        raise LedgerError("variant identity mismatch")
    rows = load(normalized_input)
    lo, hi = _evaluation_window(rows, config["evaluation_start"], config["evaluation_end"])
    warmup_lo, warmup_observations = _warmup_window(lo, strategy_id, config["parameters"])
    selected_rows = rows[warmup_lo:hi]
    _reject_timestamp_gaps(selected_rows, config["expected_interval"])
    close_all = np.array([float(row["close"]) for row in selected_rows], dtype=float)
    close = close_all[warmup_observations:]
    if not np.all(np.isfinite(close)):
        raise ValueError("non-finite close values in evaluation window")
    position_all = positions(strategy_id, close_all, config["parameters"])
    position = position_all[warmup_observations:]
    _validate_positions(position, strategy_id, config["parameters"])
    total_cost_bps = float(config["fee_bps"]) + float(config["slippage_bps"])
    metrics = _metrics(close, position, total_cost_bps)
    _validate_finite_metrics(metrics)
    run_id = output.name
    output.mkdir(parents=True, exist_ok=True)
    metrics_path = output / "metrics.json"
    metrics_path.write_bytes(_canonical_bytes(metrics) + b"\n")
    result_paths = {"metrics": str(metrics_path)}
    result_hashes = {"metrics": sha256_path(metrics_path)}
    labels = _run_labels(run_id)
    receipt = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "repository_commit": _repository_commit(),
        "relevant_source_clean": True,
        "relevant_source_sha256": source_sha256,
        "strategy_id": strategy_id,
        "symbol": _symbol_from_input(normalized_input),
        "period": labels["period"],
        "cost_mode": labels["cost_mode"],
        "strategy_version": config["strategy_version"],
        "parameters": config["parameters"],
        "candidate_id": ledger_binding["candidate_id"],
        "family_id": ledger_binding["family_id"],
        "variant_id": ledger_binding["variant_id"],
        "trial_id": ledger_binding["trial_id"],
        "research_intent": ledger_binding["research_intent"],
        "candidate_event_id": ledger_binding["candidate_event_id"],
        "latest_decision_event_id": ledger_binding["latest_decision_event_id"],
        "ledger_sha256_before_run": ledger_binding["ledger_sha256_before_run"],
        "config_sha256": sha256_path(config_path),
        "input_sha256": input_sha256,
        "funding_boundary_mode": config["funding_boundary_mode"],
        "initial_capital": float(config["initial_capital"]),
        "fee_assumption": {"fee_bps": float(config["fee_bps"])},
        "slippage_assumption": {"slippage_bps": float(config["slippage_bps"])},
        "gap_policy": config["gap_policy"],
        "expected_interval": config["expected_interval"],
        "evaluation_range": {"start": config["evaluation_start"], "end": config["evaluation_end"]},
        "warmup_range": {
            "start": selected_rows[0]["timestamp"],
            "end": rows[lo - 1]["timestamp"] if warmup_observations else None,
            "observation_count": warmup_observations,
        },
        "determinism_seed": None,
        "command": command or [],
        "result_artifact_paths": result_paths,
        "result_artifact_sha256": result_hashes,
        "status": "completed",
        "warnings": sanity_warnings(metrics),
        "exploratory_only": EXPLORATORY_ONLY,
    }
    receipt_path = output / "run_receipt.json"
    receipt_path.write_bytes(_canonical_bytes(receipt) + b"\n")
    receipt_sha256 = sha256_path(receipt_path)
    append_canonical_event(
        build_trial_completed_event(
            receipt=receipt,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
            metrics=metrics,
        ),
        research_root,
    )
    return {"metrics": metrics, "receipt": receipt, "metrics_path": metrics_path, "receipt_path": receipt_path}


def summarize_runs(run_dirs: list[Path], output_path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    warning_count = 0
    for run_dir in sorted(run_dirs):
        receipt_path = run_dir / "run_receipt.json"
        metrics_path = run_dir / "metrics.json"
        if not receipt_path.exists() or not metrics_path.exists():
            raise FileNotFoundError(f"missing run artifacts: {run_dir}")
        receipt = _load_json(receipt_path)
        metrics = _load_json(metrics_path)
        if receipt.get("result_artifact_sha256", {}).get("metrics") != sha256_path(metrics_path):
            warning_count += 1
            status = "receipt/hash mismatch"
        else:
            status = str(receipt.get("status", "UNKNOWN"))
        warnings = set(sanity_warnings(metrics)) | set(receipt.get("warnings", []))
        warning_count += len(warnings)
        row = {
            "run_id": receipt["run_id"],
            "repository_commit": receipt.get("repository_commit", ""),
            "relevant_source_sha256": receipt.get("relevant_source_sha256", ""),
            "strategy_id": receipt["strategy_id"],
            "symbol": receipt.get("symbol", ""),
            "period": receipt.get("period") or receipt["evaluation_range"]["start"][:4],
            "cost_mode": receipt.get("cost_mode") or "unknown",
            "observation_count": metrics["observation_count"],
            "trade_count": metrics["trade_count"],
            "exposure_fraction": metrics["exposure_fraction"],
            "gross_return": metrics["gross_return"],
            "net_return": metrics["net_return"],
            "buy_and_hold_return": metrics["buy_and_hold_return"],
            "excess_return_vs_buy_and_hold": metrics["excess_return_vs_buy_and_hold"],
            "total_cost": metrics["total_cost"],
            "maximum_drawdown": metrics["maximum_drawdown"],
            "status": status,
            "receipt_path": str(receipt_path),
        }
        rows.append(row)
    rows.sort(key=lambda row: (row["strategy_id"], row["symbol"], row["period"], row["cost_mode"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": rows, "warning_count": warning_count, "summary_path": output_path, "summary_sha256": sha256_path(output_path)}


def _repository_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="run one exploratory QntyLab strategy test")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--strategy", required=True)
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--overwrite", action="store_true")
    run.add_argument("--research-root", type=Path, default=RESEARCH_ROOT)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        result = run_strategy(
            strategy_id=args.strategy,
            input_path=args.input,
            config_path=args.config,
            output=args.output,
            overwrite=args.overwrite,
            research_root=args.research_root,
            command=(["python", "-m", "qntylab.strategy_test", *argv] if argv is not None else sys.argv),
        )
        print(json.dumps({"status": result["receipt"]["status"], "run_id": result["receipt"]["run_id"]}, sort_keys=True))


if __name__ == "__main__":
    main()
