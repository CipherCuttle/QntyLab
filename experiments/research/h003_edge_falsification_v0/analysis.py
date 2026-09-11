"""Result-blind diagnostics for H003_EDGE_FALSIFICATION_V0.

This module deliberately has no CLI and performs no data acquisition, ledger
mutation, strategy trial registration, or verdict publication. Official H003
research evidence remains owned by ``qntylab.strategy_test``. The functions
below validate an official completed receipt, reconstruct the exact already-
registered H003 position path through ``qntylab.strategies.positions``, and
compute only the preregistered defensive-risk controls/diagnostics.

No parameter search, replacement-winner selection, Qnty/QntySpot authority,
capital, signing, submission, or execution semantics live here.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
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
CANONICAL_DATASET_START = "2021-01-01T00:00:00Z"
RESET_FROZEN_DATASET_START = "FROZEN_DATASET_START"
RESET_MANIFEST_GAP = "MANIFEST_DECLARED_UNNORMALIZED_GAP"
AUTHORIZED_GAP_SEGMENT_STARTS = (
    "2021-02-11T05:00:00Z",
    "2021-03-06T03:00:00Z",
    "2021-04-20T04:00:00Z",
    "2021-04-25T08:00:00Z",
    "2021-08-13T06:00:00Z",
    "2021-09-29T09:00:00Z",
)


class H003FalsificationError(ValueError):
    """Fail-closed contract violation for V0 analysis."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise H003FalsificationError(message)


def _parse_utc_timestamp(value: str, *, label: str) -> datetime:
    _require(isinstance(value, str) and bool(value), f"{label} must be a non-empty timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise H003FalsificationError(f"{label} is not a valid ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None, f"{label} must be timezone-aware")
    _require(parsed.utcoffset() == timedelta(0), f"{label} must be UTC")
    return parsed.astimezone(UTC)


def _validated_timestamps(timestamps: Sequence[str] | Iterable[str], *, expected_length: int) -> tuple[tuple[str, ...], tuple[datetime, ...]]:
    values = tuple(timestamps)
    _require(len(values) == expected_length, "timestamp/close length mismatch")
    _require(len(values) >= 3, "at least 3 timestamps are required")
    parsed = tuple(_parse_utc_timestamp(value, label=f"timestamps[{index}]") for index, value in enumerate(values))
    for previous, current in zip(parsed, parsed[1:], strict=True):
        _require(current - previous == timedelta(hours=1), "attested timestamps must be strictly contiguous hourly UTC bars")
    return values, parsed


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
    ``qntylab.strategy_test`` boundary. This function does not create a trial
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
    close_values = _validated_close(close)
    return positions(STRATEGY_ID, close_values, dict(PARAMETERS))


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

    ``strategy_test`` publishes ``exposure_fraction`` over the full position
    vector, while the evaluator's ``average_absolute_exposure`` is the separate
    held-return-interval diagnostic. The distinction is intentional here.
    """

    validate_official_receipt(receipt)
    position_values = _validated_binary_position(position, expected_length=len(close))
    evaluated = evaluate_path(close, position_values, total_cost_bps=total_cost_bps_from_receipt(receipt))

    expected = {
        "observation_count": len(evaluated["net_returns"]),
        "trade_count": evaluated["trade_count"],
        "exposure_fraction": float(np.abs(position_values).mean()),
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

    close_values = _validated_close(close)
    buy_and_hold_return = float(close_values[-1] / close_values[0] - 1)
    _require("buy_and_hold_return" in official_metrics, "official metrics missing buy_and_hold_return")
    _require(
        math.isclose(
            float(official_metrics["buy_and_hold_return"]),
            buy_and_hold_return,
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ),
        "official buy_and_hold_return mismatch",
    )
    _require("excess_return_vs_buy_and_hold" in official_metrics, "official metrics missing excess_return_vs_buy_and_hold")
    expected_excess = float(evaluated["net_cumulative_return"]) - buy_and_hold_return
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


def reporting_block_slice(
    timestamps: Sequence[str] | Iterable[str],
    close: np.ndarray,
    receipt: Mapping[str, Any],
    official_metrics: Mapping[str, Any],
    *,
    expected_input_sha256: str,
    block_start: str,
    block_end: str,
    authorized_reset_reason: str | None = None,
) -> dict[str, Any]:
    """Bind an official full path, then slice returns by ending timestamp.

    Calendar/reporting boundaries never restart H003. A reset is accepted only
    at the frozen dataset start or at one of the preregistered 2021 post-gap
    segment starts. Otherwise enough prehistory must be present for the causal
    MA(48,192) predecessor position before the first owned reporting return.
    """

    _require(isinstance(expected_input_sha256, str) and len(expected_input_sha256) == 64, "expected_input_sha256 must be a 64-character digest")
    close_values = _validated_close(close)
    timestamp_values, parsed = _validated_timestamps(timestamps, expected_length=len(close_values))
    validate_official_receipt(receipt, expected_input_sha256=expected_input_sha256)

    evaluation_range = receipt["evaluation_range"]
    receipt_start = _parse_utc_timestamp(evaluation_range.get("start"), label="receipt evaluation start")
    receipt_end = _parse_utc_timestamp(evaluation_range.get("end"), label="receipt evaluation end")
    _require(receipt_start == parsed[0], "receipt evaluation start must equal supplied attested path start")
    _require(receipt_end == parsed[-1], "receipt evaluation end must equal supplied attested path end")

    full_position = reconstruct_h003_position(close_values, receipt)
    verify_official_metrics(close_values, full_position, receipt, official_metrics)

    start = _parse_utc_timestamp(block_start, label="block_start")
    end = _parse_utc_timestamp(block_end, label="block_end")
    _require(start <= end, "block_start must be at or before block_end")
    _require(parsed[0] <= start <= parsed[-1], "block_start is outside the attested path")
    _require(parsed[0] <= end <= parsed[-1], "block_end is outside the attested path")

    owned_end_indices = [index for index in range(1, len(parsed)) if start <= parsed[index] <= end]
    _require(bool(owned_end_indices), "reporting block owns no evaluable returns")
    first_end = owned_end_indices[0]
    last_end = owned_end_indices[-1]
    _require(owned_end_indices == list(range(first_end, last_end + 1)), "reporting return ownership must be contiguous")

    if start == parsed[0]:
        if authorized_reset_reason == RESET_FROZEN_DATASET_START:
            _require(parsed[0] == _parse_utc_timestamp(CANONICAL_DATASET_START, label="canonical dataset start"), "dataset-start reset is only valid at the frozen dataset start")
        elif authorized_reset_reason == RESET_MANIFEST_GAP:
            allowed = {_parse_utc_timestamp(value, label="authorized gap segment start") for value in AUTHORIZED_GAP_SEGMENT_STARTS}
            _require(parsed[0] in allowed, "manifest-gap reset start is not preregistered")
        else:
            raise H003FalsificationError("attested path begins at reporting boundary without an authorized reset reason")
    else:
        _require(authorized_reset_reason is None, "reset reason is only valid when reporting block starts at attested segment start")
        _require(parsed[first_end] == start, "non-reset reporting block must include its exact block_start timestamp")
        # The predecessor held position is causal-shifted. It must itself occur
        # after a complete slow-MA history, hence slow + 1 closes precede the
        # first owned ending timestamp. This is stricter than the frozen
        # 'at least 192 closes' floor and prevents an artificial FLAT predecessor.
        _require(first_end >= PARAMETERS["slow"] + 1, "insufficient prehistory for inherited H003 predecessor position")

    slice_start = first_end - 1
    slice_stop = last_end + 1
    return {
        "timestamps": timestamp_values[slice_start:slice_stop],
        "close": close_values[slice_start:slice_stop].copy(),
        "position": full_position[slice_start:slice_stop].copy(),
        "first_return_ending_timestamp": timestamp_values[first_end],
        "last_return_ending_timestamp": timestamp_values[last_end],
        "owned_return_count": len(owned_end_indices),
        "full_attested_position": full_position,
    }


def summarize_reporting_block(
    timestamps: Sequence[str] | Iterable[str],
    close: np.ndarray,
    receipt: Mapping[str, Any],
    official_metrics: Mapping[str, Any],
    *,
    expected_input_sha256: str,
    block_start: str,
    block_end: str,
    authorized_reset_reason: str | None = None,
    seeds: Iterable[int] = DEFAULT_SEEDS,
) -> dict[str, Any]:
    """Canonical V0 reporting entry point: attest full path, slice, summarize."""

    admitted = reporting_block_slice(
        timestamps,
        close,
        receipt,
        official_metrics,
        expected_input_sha256=expected_input_sha256,
        block_start=block_start,
        block_end=block_end,
        authorized_reset_reason=authorized_reset_reason,
    )
    diagnostics = summarize_block(
        admitted["close"],
        admitted["position"],
        total_cost_bps=total_cost_bps_from_receipt(receipt),
        seeds=seeds,
    )
    return {
        "first_return_ending_timestamp": admitted["first_return_ending_timestamp"],
        "last_return_ending_timestamp": admitted["last_return_ending_timestamp"],
        "owned_return_count": admitted["owned_return_count"],
        "diagnostics": diagnostics,
    }


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
    V0 freezes the original terminal target for evaluator compatibility; this
    can affect at most one terminal transition fee and is diagnostic convention,
    not evidence for the strategy.
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
    """Low-level diagnostics for an already continuity-safe admitted slice."""

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
