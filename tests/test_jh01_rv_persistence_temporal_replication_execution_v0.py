from __future__ import annotations

import ast
import inspect
import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from qntylab import jh01_rv_persistence_temporal_replication_execution_v0 as execution


def _window_fixture(*, unsafe_prior: bool = False):
    decision = datetime(2025, 7, 20, tzinfo=UTC)
    boundaries = [decision - timedelta(hours=index) for index in range(23, -1, -1)] + [decision + timedelta(hours=index) for index in range(1, 25)]
    returns = {boundary: 0.01 for boundary in boundaries}
    bars = {}
    for symbol in execution.UNIVERSE:
        bars[symbol] = {
            boundary - timedelta(hours=1): execution.BarClose(
                boundary - timedelta(hours=1),
                1.0,
                decision + timedelta(seconds=1) if unsafe_prior and boundary <= decision else boundary,
            )
            for boundary in boundaries
        }
    return decision, returns, bars


def _reference_hac(x: list[float], y: list[float]) -> tuple[float, float, float, tuple[float, float], float]:
    """Independent NumPy oracle: least-squares and outer-product algebra only."""
    X = np.column_stack((np.ones(len(x)), np.asarray(x)))
    beta = np.linalg.lstsq(X, np.asarray(y), rcond=None)[0]
    scores = X * (np.asarray(y) - X @ beta)[:, None]
    meat = scores.T @ scores
    for lag in range(1, 6):
        gamma = scores[lag:].T @ scores[:-lag]
        meat += (1.0 - lag / 6.0) * (gamma + gamma.T)
    covariance = np.linalg.inv(X.T @ X) @ meat @ np.linalg.inv(X.T @ X)
    standard_error = float(np.sqrt(covariance[1, 1]))
    interval = (float(beta[1] - execution.HAC_CRITICAL_VALUE_95 * standard_error), float(beta[1] + execution.HAC_CRITICAL_VALUE_95 * standard_error))
    return float(beta[0]), float(beta[1]), standard_error, interval, math.erfc(abs(float(beta[1]) / standard_error) / math.sqrt(2.0))


def test_log_returns_reject_simple_return_substitution_and_invalid_closes() -> None:
    assert execution.asset_log_return(100.0, 110.0) == pytest.approx(math.log(1.1))
    assert execution.asset_log_return(100.0, 110.0) != pytest.approx(0.1)
    for close in (0.0, -1.0, math.inf, math.nan):
        with pytest.raises(execution.ExecutionContractError):
            execution.asset_log_return(close, 1.0)


def test_market_return_requires_ordered_complete_equal_weight_panel() -> None:
    returns = {symbol: float(index) / 100.0 for index, symbol in enumerate(execution.UNIVERSE)}
    assert execution.market_hourly_return(returns) == pytest.approx(sum(returns.values()) / 20)
    with pytest.raises(execution.ExecutionContractError, match="exact ordered"):
        execution.market_hourly_return(dict(reversed(list(returns.items()))))
    with pytest.raises(execution.ExecutionContractError):
        execution.market_hourly_return(dict(list(returns.items())[:-1]))
    with pytest.raises(execution.ExecutionContractError):
        execution.market_hourly_return({**returns, "BTCUSDT": 0.1})


def test_rv24_requires_exact_nonoverlapping_return_windows() -> None:
    assert execution.market_rv24([0.01] * 24) == pytest.approx(math.sqrt(24 * 0.01**2))
    with pytest.raises(execution.ExecutionContractError):
        execution.market_rv24([0.01] * 23)
    with pytest.raises(execution.ExecutionContractError):
        execution.market_rv24([0.01] * 25)


def test_exact_prior_future_windows_and_safe_known_semantics() -> None:
    decision, returns, bars = _window_fixture()
    prior, future = execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars=bars)
    assert len(prior) == len(future) == 24
    assert prior[-1] == decision and future[0] == decision + timedelta(hours=1)
    assert prior[0] == decision - timedelta(hours=23) and future[-1] == decision + timedelta(hours=24)
    assert not set(prior) & set(future)
    _, _, unsafe_bars = _window_fixture(unsafe_prior=True)
    with pytest.raises(execution.ExecutionContractError, match="safely known"):
        execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars=unsafe_bars)


def test_panel_rejects_19_21_symbols_at_the_window_gate() -> None:
    decision, returns, bars = _window_fixture()
    with pytest.raises(execution.ExecutionContractError):
        execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars=dict(list(bars.items())[:-1]))
    with pytest.raises(execution.ExecutionContractError):
        execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars={**bars, "BTCUSDT": bars[execution.UNIVERSE[0]]})


def test_exact_365_intercept_hac5_matches_independent_numpy_oracle() -> None:
    x = [0.2 + index / 1000.0 + 0.03 * math.sin(index / 11.0) for index in range(365)]
    y = [0.05 + 0.7 * value + 0.02 * math.cos(index / 7.0) for index, value in enumerate(x)]
    actual = execution.ols_hac5(x, y)
    alpha, beta, standard_error, interval, p_value = _reference_hac(x, y)
    assert actual["alpha"] == pytest.approx(alpha, rel=0, abs=1e-13)
    assert actual["beta"] == pytest.approx(beta, rel=0, abs=1e-13)
    assert actual["hac_standard_error"] == pytest.approx(standard_error, rel=0, abs=1e-13)
    assert actual["confidence_interval_95"] == pytest.approx(interval, rel=0, abs=1e-13)
    assert actual["raw_p_value_two_sided"] == pytest.approx(p_value, rel=0, abs=1e-13)
    assert actual["hac_lag"] == 5
    assert actual["hac_covariance"] == "BARTLETT_NEWEY_WEST"


@pytest.mark.parametrize("size", [364, 366])
def test_ols_rejects_anything_but_365_rows(size: int) -> None:
    with pytest.raises(execution.ExecutionContractError, match="365"):
        execution.ols_hac5([float(index) for index in range(size)], [float(index) for index in range(size)])


def test_ols_requires_intercept_and_has_exact_bartlett_weights() -> None:
    x = [float(index) for index in range(365)]
    y = [3.0 + 2.0 * value + (0.1 if index % 2 else -0.1) for index, value in enumerate(x)]
    result = execution.ols_hac5(x, y)
    assert result["alpha"] == pytest.approx(3.0, abs=0.001)
    assert result["beta"] == pytest.approx(2.0, abs=0.0001)
    assert [1.0 - lag / (execution.HAC_LAG + 1) for lag in range(1, 6)] == pytest.approx([5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6])


@pytest.mark.parametrize(
    ("beta", "interval", "p_value", "expected"),
    [
        (0.2, (0.01, 0.4), 0.05, "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE"),
        (-0.2, (-0.4, -0.01), 0.05, "OPPOSITE_DIRECTION_WITHIN_FROZEN_TEMPORAL_SCOPE"),
        (0.2, (-0.01, 0.4), 0.001, "INCONCLUSIVE"),
        (0.2, (0.01, 0.4), 0.051, "INCONCLUSIVE"),
    ],
)
def test_classification_is_mechanical_raw_p_only(beta, interval, p_value, expected) -> None:
    assert execution.classify(beta=beta, confidence_interval_95=interval, raw_p_value_two_sided=p_value) == expected


def test_implementation_has_no_network_or_alternative_model_path() -> None:
    source = inspect.getsource(execution)
    tree = ast.parse(source)
    names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not {"requests", "urllib", "urlopen", "wget", "curl", "statsmodels", "holm", "bonferroni"} & names
    assert "alternative" not in source.lower()
    assert "execution_count\": 1" in source


def test_result_digest_is_deterministic_and_classification_is_not_caller_supplied() -> None:
    payload = {"beta": 0.1, "classification": "INCONCLUSIVE", "execution_result_digest": "ignored"}
    assert execution.digest(payload, omitted_field="execution_result_digest") == execution.digest(dict(payload), omitted_field="execution_result_digest")
    assert "classification" not in inspect.signature(execution.execute_once).parameters
