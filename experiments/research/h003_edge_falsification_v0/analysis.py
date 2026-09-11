"""Result-blind diagnostics for H003_EDGE_FALSIFICATION_V0.

This module deliberately has no CLI and performs no data acquisition, ledger
mutation, strategy trial registration, or verdict publication.  Official H003
research evidence remains owned by ``qntylab.strategy_test``.  The functions
below validate an official completed receipt, reconstruct the exact already-
registered H003 position path through ``qntylab.strategies.positions``, and
compute only the preregistered defensive-risk controls/diagnostics.

No parameter search, replacement-winner selection, Qnty/QntySpot authority,
capital, signing, submission, or execution semantics live here.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from qntylab.backtest import evaluate
from qntylab.strategies import positions

CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
STRATEGY_ID = "H003_moving_average"
STRATEGY_VERSION = "existing-qntylab-strategies-v1"
PARAMETERS = {"fast": 48, "slow": 192, "mode": "long_flat"}
SYMBOL = "SOLUSDT"
EXPECTED_INTERVAL = "1h"
FUNDING_BOUNDARY_MODE = "NOT_APPLICABLE"
GAP_POLICY = "REJECT"
RESEARCH_INTENT = "FOLLOW_UP"
DEFAULT_SEEDS = (17011, 17029, 17041, 17053, 17077, 17093, 17107, 17123, 17137, 17159)
BLOCK_HOURS = 168
DELAY_HOURS = 24


class H003FalsificationError(ValueError):
    """Fail-closed contract violation for V0 analysis."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise H003FalsificationError(message)


def validate_official_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_input_sha256: str | None = None,
    expected_start: str | None = None,
    expected_end: str | None = None,
    expected_fee_bps: float | None = None,
    expected_slippage_bps: float | None = None,
) -> None:
    """Validate the identity/accounting fields required before diagnostics.

    The receipt must already have been produced by the official
    ``qntylab.strategy_test`` boundary.  This function does not create a trial
    and intentionally does not accept alternate H003 parameters or variants.
    """

    exact = {
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "symbol": SYMBOL,
        "expected_interval": EXPECTED_INTERVAL,
        "funding_boundary_mode": FUNDING_BOUNDARY_MODE,
        "gap_policy": GAP_POLICY,
        "research_intent": RESEARCH_INTENT,
        "status": "completed",
    }
    for key, value in exact.items():
        _require(receipt.get(key) == value, f"receipt {key} must be {value!r}")

    _require(receipt.get("parameters") == PARAMETERS, "receipt parameters must be exact H003 48/192 long_flat")
    _require(receipt.get("exploratory_only") is True, "receipt must remain exploratory_only")

    fee = receipt.get("fee_assumption", {}).get("fee_bps")
    slippage = receipt.get("slippage_assumption", {}).get("slippage_bps")
    _require(isinstance(fee, (int, float)) and math.isfinite(float(fee)) and float(fee) >= 0, "receipt fee_bps invalid")
    _require(
        isinstance(slippage, (int, float)) and math.isfinite(float(slippage)) and float(slippage) >= 0,
        "receipt slippage_bps invalid",
    )

    if expected_input_sha256 is not None:
        _require(receipt.get("input_sha256") == expected_input_sha256, "receipt input_sha256 mismatch")
    evaluation_range = receipt.get("evaluation_range")
    _require(isinstance(evaluation_range, Mapping), "receipt evaluation_range missing")
    if expected_start is not None:
        _require(evaluation_range.get("start") == expected_start, "receipt evaluation start mismatch")
    if expected_end is not None:
        _require(evaluation_range.get("end") == expected_end, "receipt evaluation end mismatch")
    if expected_fee_bps is not None:
        _require(float(fee) == float(expected_fee_bps), "receipt fee_bps mismatch")
    if expected_slippage_bps is not None:
        _require(float(slippage) == float(expected_slippage_bps), "receipt slippage_bps mismatch")


def total_cost_bps_from_receipt(receipt: Mapping[str, Any]) -> float:
    validate_official_receipt(receipt)
    return float(receipt["fee_assumption"]["fee_bps"]) + float(receipt["slippage_assumption"]["slippage_bps"])


def reconstruct_h003_position(close: np.ndarray, receipt: Mapping[str, Any]) -> np.ndarray:
    """Reconstruct the exact registered position callable after receipt validation."""

    validate_official_receipt(receipt)
    close = _validated_close(close)
    return positions(STRATEGY_ID, close, dict(PARAMETERS))


def _validated_close(close: np.ndarray) -> np.ndarray:
    values = np.asarray(close, dtype=float)
    _require(values.ndim == 1 and len(values) >= 3, "close must be a one-dimensional series with at least 3 rows")
    _require(bool(np.isfinite(values).all()), "close contains non-finite values")
    _require(bool((values > 0).all()), "close values must be positive")
    return values


def _validated_binary_position(position: np.ndarray, *, expected_length: int | None = None) -> np.ndarray:
    values = np.asarray(position, dtype=float)
    _require(values.ndim == 1 and len(values) >= 3, "position must be a one-dimensional series with at least 3 rows")
    if expected_length is not None:
        _require(len(values) == expected_length, "close/position length mismatch")
    _require(bool(np.isfinite(values).all()), "position contains non-finite values")
    _require(bool(np.isin(values, (0.0, 1.0)).all()), "V0 position path must be binary long/flat")
    return values


def evaluate_path(close: np.ndarray, position: np.ndarray, *, total_cost_bps: float) -> dict[str, Any]:
    """Use QntyLab's existing evaluator and add the frozen Calmar diagnostic."""

    close_values = _validated_close(close)
    position_values = _validated_binary_position(position, expected_length=len(close_values))
    _require(math.isfinite(float(total_cost_bps)) and float(total_cost_bps) >= 0, "total_cost_bps must be finite and non-negative")

    result = dict(evaluate(close_values, position_values, float(total_cost_bps)))
    annualized_return = result["annualized_return"]
    max_drawdown = result["max_drawdown"]
    if annualized_return is None or max_drawdown == 0:
        calmar = None
    else:
        calmar = float(annualized_return) / abs(float(max_drawdown))
    result["calmar"] = calmar
    return result


def verify_official_metrics(
    close: np.ndarray,
    position: np.ndarray,
    receipt: Mapping[str, Any],
    official_metrics: Mapping[str, Any],
    *,
    absolute_tolerance: float = 1e-12,
) -> dict[str, Any]:
    """Fail closed unless reconstructed accounting matches official metrics.

    ``strategy_test`` currently publishes the compact metrics below rather than
    Sharpe/Calmar.  Matching them proves that the reconstructed path uses the
    same causal position and cost accounting before additional diagnostics are
    considered.
    """

    validate_official_receipt(receipt)
    evaluated = evaluate_path(close, position, total_cost_bps=total_cost_bps_from_receipt(receipt))

    expected = {
        "observation_count": len(evaluated["net_returns"]),
        "trade_count": evaluated["trade_count"],
        "exposure_fraction": evaluated["average_absolute_exposure"],
        "gross_return": evaluated["gross_cumulative_return"],
        "net_return": evaluated["net_cumulative_return"],
        "total_cost": evaluated["fee_cost"],
        "maximum_drawdown": evaluated["max_drawdown"],
    }
    for key, value in expected.items():
        _require(key in official_metrics, f"official metrics missing {key}")
        observed = official_metrics[key]
        if isinstance(value, int):
            _require(observed == value, f"official metric mismatch: {key}")
        else:
            _require(
                math.isclose(float(observed), float(value), rel_tol=0.0, abs_tol=absolute_tolerance),
                f"official metric mismatch: {key}",
            )

    buy_hold = evaluate_path(close, np.ones(len(close), dtype=float), total_cost_bps=0.0)
    _require("buy_and_hold_return" in official_metrics, "official metrics missing buy_and_hold_return")
    _require(
        math.isclose(
            float(official_metrics["buy_and_hold_return"]),
            float(buy_hold["net_cumulative_return"]),
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ),
        "official buy_and_hold_return mismatch",
    )
    _require("excess_return_vs_buy_and_hold" in official_metrics, "official metrics missing excess_return_vs_buy_and_hold")
    expected_excess = float(evaluated["net_cumulative_return"]) - float(buy_hold["net_cumulative_return"])
    _require(
        math.isclose(
            float(official_metrics["excess_return_vs_buy_and_hold"]),
            expected_excess,
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ),
        "official excess_return_vs_buy_and_hold mismatch",
    )
    return evaluated


def _run_length_encode(binary: np.ndarray) -> tuple[list[int], list[int]]:
    values = np.asarray(binary, dtype=int)
    _require(values.ndim == 1 and len(values) > 0, "cannot encode an empty position path")
    _require(bool(np.isin(values, (0, 1)).all()), "run-length input must be binary")

    states = [int(values[0])]
    lengths = [1]
    for value in values[1:]:
        state = int(value)
        if state == states[-1]:
            lengths[-1] += 1
        else:
            states.append(state)
            lengths.append(1)
    return states, lengths


def exposure_matched_random_position(position: np.ndarray, *, seed: int) -> np.ndarray:
    """Permute same-state holding-run lengths while preserving exact exposure.

    The preregistered control operates on the *held* path ``position[:-1]``.
    The original terminal target ``position[-1]`` is retained so the existing
    evaluator applies its normal terminal position-change accounting without
    inventing a new terminal target.
    """

    original = _validated_binary_position(position)
    held = original[:-1].astype(int)
    states, lengths = _run_length_encode(held)
    by_state = {
        0: [length for state, length in zip(states, lengths, strict=True) if state == 0],
        1: [length for state, length in zip(states, lengths, strict=True) if state == 1],
    }
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    shuffled = {
        state: list(rng.permutation(lengths_for_state)) if lengths_for_state else []
        for state, lengths_for_state in by_state.items()
    }
    offsets = {0: 0, 1: 0}
    pieces: list[np.ndarray] = []
    for state in states:
        index = offsets[state]
        run_length = int(shuffled[state][index])
        offsets[state] += 1
        pieces.append(np.full(run_length, float(state), dtype=float))
    reconstructed_held = np.concatenate(pieces)

    _require(len(reconstructed_held) == len(held), "exposure-matched control length changed")
    _require(int(reconstructed_held.sum()) == int(held.sum()), "exposure-matched control changed long exposure")
    _, reconstructed_lengths = _run_length_encode(reconstructed_held.astype(int))
    reconstructed_states, _ = _run_length_encode(reconstructed_held.astype(int))
    _require(reconstructed_states == states, "exposure-matched control changed alternating state order")
    for state in (0, 1):
        original_state_lengths = sorted(length for s, length in zip(states, lengths, strict=True) if s == state)
        new_state_lengths = sorted(
            length for s, length in zip(reconstructed_states, reconstructed_lengths, strict=True) if s == state
        )
        _require(original_state_lengths == new_state_lengths, "exposure-matched control changed run-length multiset")

    return np.r_[reconstructed_held, original[-1]]


def block_shuffled_position(position: np.ndarray, *, seed: int, block_hours: int = BLOCK_HOURS) -> np.ndarray:
    """Permute full 168-hour held-position blocks; keep the partial tail fixed."""

    original = _validated_binary_position(position)
    _require(isinstance(block_hours, int) and block_hours > 0, "block_hours must be a positive integer")
    held = original[:-1]
    full_count = len(held) // block_hours
    full_length = full_count * block_hours
    full = held[:full_length]
    tail = held[full_length:]

    if full_count <= 1:
        reconstructed = held.copy()
    else:
        blocks = full.reshape(full_count, block_hours)
        rng = np.random.Generator(np.random.PCG64(int(seed)))
        order = rng.permutation(full_count)
        reconstructed = np.concatenate([blocks[order].reshape(-1), tail])

    _require(len(reconstructed) == len(held), "block-shuffled control length changed")
    return np.r_[reconstructed, original[-1]]


def delayed_position(position: np.ndarray, *, delay_hours: int = DELAY_HOURS) -> np.ndarray:
    """Delay the exact full H003 position path by 24 completed hourly bars."""

    original = _validated_binary_position(position)
    _require(isinstance(delay_hours, int) and delay_hours > 0, "delay_hours must be a positive integer")
    delayed = np.zeros_like(original)
    if delay_hours < len(original):
        delayed[delay_hours:] = original[:-delay_hours]
    return delayed


def _median_metric(rows: Iterable[Mapping[str, Any]], metric: str) -> float | None:
    values = [row[metric] for row in rows]
    if any(value is None for value in values):
        return None
    return float(np.median(np.asarray(values, dtype=float)))


def summarize_block(
    close: np.ndarray,
    h003_position: np.ndarray,
    *,
    total_cost_bps: float,
    seeds: Iterable[int] = DEFAULT_SEEDS,
) -> dict[str, Any]:
    """Compute preregistered diagnostics for one already-admitted contiguous block."""

    close_values = _validated_close(close)
    position_values = _validated_binary_position(h003_position, expected_length=len(close_values))
    seed_values = tuple(int(seed) for seed in seeds)
    _require(seed_values == DEFAULT_SEEDS, "V0 seeds must equal the preregistered seed set")

    h003 = evaluate_path(close_values, position_values, total_cost_bps=total_cost_bps)
    buy_hold = evaluate_path(close_values, np.ones(len(close_values), dtype=float), total_cost_bps=0.0)
    delayed = evaluate_path(close_values, delayed_position(position_values), total_cost_bps=total_cost_bps)

    exposure_rows = [
        evaluate_path(close_values, exposure_matched_random_position(position_values, seed=seed), total_cost_bps=total_cost_bps)
        for seed in seed_values
    ]
    block_rows = [
        evaluate_path(close_values, block_shuffled_position(position_values, seed=seed), total_cost_bps=total_cost_bps)
        for seed in seed_values
    ]
    median_metrics = (
        "sharpe",
        "calmar",
        "max_drawdown",
        "net_cumulative_return",
        "average_absolute_exposure",
        "turnover",
        "trade_count",
    )

    return {
        "h003": h003,
        "buy_and_hold": buy_hold,
        "cash": {"net_cumulative_return": 0.0, "sharpe": None, "calmar": None, "max_drawdown": 0.0},
        "delayed_24h": delayed,
        "exposure_matched_random": {
            "seeds": list(seed_values),
            "rows": exposure_rows,
            "median": {metric: _median_metric(exposure_rows, metric) for metric in median_metrics},
        },
        "block_shuffled_168h": {
            "seeds": list(seed_values),
            "rows": block_rows,
            "median": {metric: _median_metric(block_rows, metric) for metric in median_metrics},
        },
    }
