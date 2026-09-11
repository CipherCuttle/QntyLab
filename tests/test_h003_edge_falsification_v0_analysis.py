from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from experiments.research.h003_edge_falsification_v0.analysis import (
    BLOCK_HOURS,
    CANDIDATE_ID,
    DEFAULT_SEEDS,
    DELAY_HOURS,
    H003FalsificationError,
    PARAMETERS,
    RESET_FROZEN_DATASET_START,
    STRATEGY_ID,
    STRATEGY_VERSION,
    VARIANT_ID,
    block_shuffled_position,
    delayed_position,
    evaluate_path,
    exposure_matched_random_position,
    reconstruct_h003_position,
    reporting_block_slice,
    summarize_block,
    summarize_reporting_block,
    total_cost_bps_from_receipt,
    validate_official_receipt,
    verify_official_metrics,
)
from qntylab.backtest import evaluate


def _receipt(
    *,
    fee_bps: float = 10.0,
    slippage_bps: float = 0.0,
    input_sha256: str = "a" * 64,
    start: str = "2024-01-01T00:00:00Z",
    end: str = "2024-12-31T23:00:00Z",
) -> dict:
    return {
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "symbol": "SOLUSDT",
        "expected_interval": "1h",
        "funding_boundary_mode": "NOT_APPLICABLE",
        "gap_policy": "REJECT",
        "research_intent": "FOLLOW_UP",
        "status": "completed",
        "parameters": dict(PARAMETERS),
        "exploratory_only": True,
        "input_sha256": input_sha256,
        "evaluation_range": {"start": start, "end": end},
        "fee_assumption": {"fee_bps": fee_bps},
        "slippage_assumption": {"slippage_bps": slippage_bps},
    }


def _synthetic_close(n: int = 720) -> np.ndarray:
    # Deterministic multi-regime path: enough observations for MA(48,192), with
    # both trend and reversal structure but no market-data claim.
    x = np.arange(n, dtype=float)
    log_close = 4.5 + 0.0009 * x + 0.08 * np.sin(x / 37.0) + 0.035 * np.sin(x / 11.0)
    return np.exp(log_close)


def _monotonic_close(n: int = 520) -> np.ndarray:
    return np.linspace(100.0, 220.0, n, dtype=float)


def _timestamps(n: int, *, start: datetime = datetime(2024, 1, 1, tzinfo=UTC)) -> list[str]:
    return [(start + timedelta(hours=index)).isoformat().replace("+00:00", "Z") for index in range(n)]


def _official_metrics(close: np.ndarray, position: np.ndarray, total_cost_bps: float) -> dict:
    evaluated = evaluate(close, position, total_cost_bps)
    buy_hold = float(close[-1] / close[0] - 1)
    return {
        "observation_count": len(evaluated["net_returns"]),
        "trade_count": evaluated["trade_count"],
        "exposure_fraction": float(np.abs(position).mean()),
        "gross_return": evaluated["gross_cumulative_return"],
        "net_return": evaluated["net_cumulative_return"],
        "buy_and_hold_return": buy_hold,
        "excess_return_vs_buy_and_hold": evaluated["net_cumulative_return"] - buy_hold,
        "total_cost": evaluated["fee_cost"],
        "maximum_drawdown": evaluated["max_drawdown"],
    }


def _control_position() -> np.ndarray:
    # Multiple runs of both states are required so run-length permutations are
    # meaningfully testable. Last element is the frozen terminal-target
    # convention used by the V0 controls.
    held = np.array(
        [0] * 4
        + [1] * 3
        + [0] * 2
        + [1] * 5
        + [0] * 6
        + [1] * 2
        + [0] * 3
        + [1] * 4,
        dtype=float,
    )
    return np.r_[held, 0.0]


def _run_lengths(values: np.ndarray, state: int) -> list[int]:
    result: list[int] = []
    current = int(values[0])
    length = 1
    for value in values[1:]:
        value_i = int(value)
        if value_i == current:
            length += 1
        else:
            if current == state:
                result.append(length)
            current = value_i
            length = 1
    if current == state:
        result.append(length)
    return sorted(result)


def test_receipt_validator_binds_exact_h003_identity_and_accounting() -> None:
    receipt = _receipt(fee_bps=10.0, slippage_bps=10.0)
    validate_official_receipt(
        receipt,
        expected_input_sha256="a" * 64,
        expected_start="2024-01-01T00:00:00Z",
        expected_end="2024-12-31T23:00:00Z",
        expected_fee_bps=10.0,
        expected_slippage_bps=10.0,
    )
    assert total_cost_bps_from_receipt(receipt) == 20.0

    for field, bad_value in (
        ("candidate_id", "OTHER"),
        ("variant_id", "variant_other"),
        ("strategy_id", "H002_momentum"),
        ("strategy_version", "other-version"),
        ("symbol", "BTCUSDT"),
        ("research_intent", "SCREEN"),
        ("status", "failed"),
    ):
        bad = copy.deepcopy(receipt)
        bad[field] = bad_value
        with pytest.raises(H003FalsificationError):
            validate_official_receipt(bad)

    bad_params = copy.deepcopy(receipt)
    bad_params["parameters"]["fast"] = 49
    with pytest.raises(H003FalsificationError):
        validate_official_receipt(bad_params)


def test_reconstruction_uses_existing_h003_callable_and_existing_evaluator() -> None:
    close = _synthetic_close()
    receipt = _receipt(fee_bps=10.0, slippage_bps=10.0)
    position = reconstruct_h003_position(close, receipt)

    assert len(position) == len(close)
    assert set(np.unique(position)).issubset({0.0, 1.0})
    assert np.all(position[:192] == 0.0)

    ours = evaluate_path(close, position, total_cost_bps=20.0)
    canonical = evaluate(close, position, 20.0)
    for key in (
        "net_cumulative_return",
        "annualized_return",
        "sharpe",
        "max_drawdown",
        "trade_count",
        "turnover",
        "average_absolute_exposure",
        "fee_cost",
        "net_returns",
    ):
        assert ours[key] == canonical[key]

    if ours["annualized_return"] is not None and ours["max_drawdown"] != 0:
        assert ours["calmar"] == pytest.approx(ours["annualized_return"] / abs(ours["max_drawdown"]), rel=0, abs=1e-15)


def test_official_metric_crosscheck_uses_strategy_test_exposure_semantics() -> None:
    close = _monotonic_close(n=320)
    receipt = _receipt(fee_bps=10.0, slippage_bps=0.0)
    position = reconstruct_h003_position(close, receipt)
    evaluated = evaluate(close, position, 10.0)
    official = _official_metrics(close, position, 10.0)

    assert position[-1] == 1.0
    assert official["exposure_fraction"] == pytest.approx(float(np.abs(position).mean()))
    assert official["exposure_fraction"] != pytest.approx(evaluated["average_absolute_exposure"], abs=1e-15)

    verified = verify_official_metrics(close, position, receipt, official)
    assert verified["net_cumulative_return"] == evaluated["net_cumulative_return"]

    for key in ("trade_count", "exposure_fraction", "net_return", "maximum_drawdown", "buy_and_hold_return"):
        corrupted = dict(official)
        corrupted[key] = corrupted[key] + 1 if key == "trade_count" else float(corrupted[key]) + 1e-6
        with pytest.raises(H003FalsificationError, match="mismatch"):
            verify_official_metrics(close, position, receipt, corrupted)


def test_reporting_slice_reconstructs_full_path_before_calendar_slice() -> None:
    close = _monotonic_close(n=520)
    timestamps = _timestamps(len(close))
    receipt = _receipt(start=timestamps[0], end=timestamps[-1])
    full_position = reconstruct_h003_position(close, receipt)
    official = _official_metrics(close, full_position, 10.0)
    first_end = 300
    last_end = 500

    admitted = reporting_block_slice(
        timestamps,
        close,
        receipt,
        official,
        expected_input_sha256="a" * 64,
        block_start=timestamps[first_end],
        block_end=timestamps[last_end],
    )

    assert admitted["timestamps"][0] == timestamps[first_end - 1]
    assert admitted["timestamps"][1] == timestamps[first_end]
    assert admitted["first_return_ending_timestamp"] == timestamps[first_end]
    assert admitted["last_return_ending_timestamp"] == timestamps[last_end]
    assert admitted["owned_return_count"] == last_end - first_end + 1
    assert admitted["position"][0] == full_position[first_end - 1] == 1.0
    assert np.array_equal(admitted["position"], full_position[first_end - 1 : last_end + 1])

    expected = evaluate(
        close[first_end - 1 : last_end + 1],
        full_position[first_end - 1 : last_end + 1],
        10.0,
    )
    observed = evaluate_path(admitted["close"], admitted["position"], total_cost_bps=10.0)
    assert np.array_equal(observed["net_returns"], expected["net_returns"])

    naive_restart = reconstruct_h003_position(admitted["close"], receipt)
    assert naive_restart[0] == 0.0
    assert admitted["position"][0] == 1.0

    summary = summarize_reporting_block(
        timestamps,
        close,
        receipt,
        official,
        expected_input_sha256="a" * 64,
        block_start=timestamps[first_end],
        block_end=timestamps[last_end],
    )
    assert summary["owned_return_count"] == last_end - first_end + 1
    assert summary["diagnostics"]["h003"]["net_cumulative_return"] == observed["net_cumulative_return"]


def test_reporting_slice_rejects_artificial_reset_insufficient_history_and_gaps() -> None:
    close = _monotonic_close(n=260)
    timestamps = _timestamps(len(close))
    receipt = _receipt(start=timestamps[0], end=timestamps[-1])
    position = reconstruct_h003_position(close, receipt)
    official = _official_metrics(close, position, 10.0)

    with pytest.raises(H003FalsificationError, match="insufficient prehistory"):
        reporting_block_slice(
            timestamps,
            close,
            receipt,
            official,
            expected_input_sha256="a" * 64,
            block_start=timestamps[192],
            block_end=timestamps[-1],
        )

    with pytest.raises(H003FalsificationError, match="authorized reset reason"):
        reporting_block_slice(
            timestamps,
            close,
            receipt,
            official,
            expected_input_sha256="a" * 64,
            block_start=timestamps[0],
            block_end=timestamps[-1],
        )

    broken = list(timestamps)
    broken[220] = (datetime.fromisoformat(broken[220].replace("Z", "+00:00")) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(H003FalsificationError, match="strictly contiguous hourly"):
        reporting_block_slice(
            broken,
            close,
            receipt,
            official,
            expected_input_sha256="a" * 64,
            block_start=broken[200],
            block_end=broken[-1],
        )


def test_dataset_start_reset_is_explicit_and_frozen() -> None:
    close = _monotonic_close(n=260)
    timestamps = _timestamps(len(close), start=datetime(2021, 1, 1, tzinfo=UTC))
    receipt = _receipt(start=timestamps[0], end=timestamps[-1])
    position = reconstruct_h003_position(close, receipt)
    official = _official_metrics(close, position, 10.0)

    admitted = reporting_block_slice(
        timestamps,
        close,
        receipt,
        official,
        expected_input_sha256="a" * 64,
        block_start=timestamps[0],
        block_end=timestamps[-1],
        authorized_reset_reason=RESET_FROZEN_DATASET_START,
    )
    assert admitted["first_return_ending_timestamp"] == timestamps[1]
    assert admitted["owned_return_count"] == len(close) - 1


def test_exposure_matched_control_preserves_exact_held_exposure_and_run_multisets() -> None:
    position = _control_position()
    original_held = position[:-1]

    a = exposure_matched_random_position(position, seed=17011)
    b = exposure_matched_random_position(position, seed=17011)
    c = exposure_matched_random_position(position, seed=17029)

    assert np.array_equal(a, b)
    assert len(a) == len(position)
    assert a[-1] == position[-1]
    assert int(a[:-1].sum()) == int(original_held.sum())
    assert _run_lengths(a[:-1], 0) == _run_lengths(original_held, 0)
    assert _run_lengths(a[:-1], 1) == _run_lengths(original_held, 1)
    assert not np.array_equal(a, position)
    assert not np.array_equal(a, c)


def test_block_shuffle_preserves_full_blocks_and_keeps_partial_tail_and_terminal_target() -> None:
    held = np.tile(np.r_[np.zeros(84), np.ones(84)], 4)
    tail = np.r_[np.ones(13), np.zeros(9)]
    position = np.r_[held, tail, 1.0]

    shuffled = block_shuffled_position(position, seed=17011, block_hours=BLOCK_HOURS)
    assert len(shuffled) == len(position)
    assert np.array_equal(shuffled[-(len(tail) + 1) : -1], tail)
    assert shuffled[-1] == position[-1]

    original_blocks = position[:-1][: len(held)].reshape(-1, BLOCK_HOURS)
    shuffled_blocks = shuffled[:-1][: len(held)].reshape(-1, BLOCK_HOURS)
    assert sorted(block.tobytes() for block in original_blocks) == sorted(block.tobytes() for block in shuffled_blocks)


def test_delayed_control_is_exact_24_bar_shift_with_no_lookahead() -> None:
    position = _control_position()
    delayed = delayed_position(position, delay_hours=DELAY_HOURS)

    assert np.all(delayed[:DELAY_HOURS] == 0.0)
    assert np.array_equal(delayed[DELAY_HOURS:], position[:-DELAY_HOURS])


def test_summary_uses_frozen_seeds_zero_cost_buy_hold_and_frozen_controls() -> None:
    close = _synthetic_close(n=900)
    receipt = _receipt(fee_bps=10.0, slippage_bps=10.0)
    position = reconstruct_h003_position(close, receipt)

    summary = summarize_block(close, position, total_cost_bps=20.0)

    assert summary["exposure_matched_random"]["seeds"] == list(DEFAULT_SEEDS)
    assert summary["block_shuffled_168h"]["seeds"] == list(DEFAULT_SEEDS)
    assert len(summary["exposure_matched_random"]["rows"]) == 10
    assert len(summary["block_shuffled_168h"]["rows"]) == 10
    assert summary["buy_and_hold"]["fee_cost"] == 0.0
    assert summary["cash"] == {
        "net_cumulative_return": 0.0,
        "sharpe": None,
        "calmar": None,
        "max_drawdown": 0.0,
    }

    expected_h003 = evaluate(close, position, 20.0)
    assert summary["h003"]["net_cumulative_return"] == expected_h003["net_cumulative_return"]
    assert summary["h003"]["fee_cost"] == expected_h003["fee_cost"]

    median_sharpe = np.median([row["sharpe"] for row in summary["exposure_matched_random"]["rows"]])
    assert summary["exposure_matched_random"]["median"]["sharpe"] == pytest.approx(median_sharpe)


def test_analysis_module_contains_no_data_acquisition_or_execution_surface() -> None:
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "experiments/research/h003_edge_falsification_v0/analysis.py"
    ).read_text(encoding="utf-8")

    forbidden_code_tokens = (
        "import requests",
        "from requests",
        "import urllib",
        "import socket",
        "subprocess.",
        "private_key",
        "sign_transaction",
        "send_transaction",
        "submit_transaction",
        "web3.",
    )
    for token in forbidden_code_tokens:
        assert token not in source

    assert "argparse" not in source
    assert "if __name__ ==" not in source
