import numpy as np
import pytest

from qntylab.clean_tsmom import (
    SYMBOLS,
    aggregate_8h,
    completed_returns_at_decision_close,
    signal,
    weights_v1,
    weights_v2,
)


def panel(bars=140):
    closes = np.ones((bars, len(SYMBOLS)))
    for i in range(1, bars):
        closes[i, 0] = closes[i - 1, 0] * 1.002
        closes[i, 1] = closes[i - 1, 1] * (1.02 if i % 2 else 0.98)
        closes[i, 2:] = closes[i - 1, 2:] * 1.001
    closes[20:, :2] *= 1.01
    return closes


def test_signal_boundary_and_v1_unchanged():
    close = np.ones(23)
    close[20:] = 2
    assert signal(close)[:20].sum() == 0
    assert signal(close)[20] == 1
    closes = np.ones((30, len(SYMBOLS)))
    closes[20:, :5] = 2
    weights = weights_v1(closes)
    assert np.allclose(weights[20, :5], 1 / 9)
    assert np.all(weights.sum(axis=1) <= 1)


def test_v2_future_mutation_cannot_change_current_weight():
    closes = panel()
    before, _ = weights_v2(closes)
    mutated = closes.copy()
    mutated[101:] *= np.array([3.0] * len(SYMBOLS))
    after, _ = weights_v2(mutated)
    assert np.allclose(before[100], after[100])


def test_v2_eligible_return_mutation_can_change_current_weight():
    closes = panel()
    before, _ = weights_v2(closes)
    mutated = closes.copy()
    mutated[99, 2] *= 10.0
    after, _ = weights_v2(mutated)
    assert np.max(np.abs(before[100] - after[100])) > 1e-6


def test_exactly_90_completed_returns_and_no_t_plus_one():
    closes = panel()
    returns = completed_returns_at_decision_close(closes, 100)
    assert returns.shape == (90, len(SYMBOLS))
    expected = np.log(closes[100] / closes[99])
    assert np.allclose(returns[-1], expected)
    leaked = np.log(closes[101] / closes[100])
    assert not np.allclose(returns[-1], leaked)
    with pytest.raises(ValueError):
        completed_returns_at_decision_close(closes, 89)


def test_population_std_and_no_same_bar_execution_contract():
    closes = panel()
    weights, _ = weights_v2(closes)
    returns = completed_returns_at_decision_close(closes, 100)
    assert np.allclose(np.std(returns, axis=0, ddof=0), np.std(returns, axis=0))
    assert np.allclose(weights[100], weights_v2(closes)[0][100])
    assert np.all(weights.sum(axis=1) <= 1 + 1e-12)


def test_aggregate_rejects_gap_duplicate_and_off_grid():
    def rows(stamps):
        return [{"timestamp": t, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for t in stamps]

    base = list(range(0, 8 * 3_600_000, 3_600_000))
    assert aggregate_8h(rows(base))[0]["timestamp"] == 0
    with pytest.raises(ValueError):
        aggregate_8h(rows(base[:-1] + [base[-1] + 7_200_000]))
    with pytest.raises(ValueError):
        aggregate_8h(rows(base[:-1] + [base[-2]]))
    with pytest.raises(ValueError):
        aggregate_8h(rows([3_600_000 + x for x in base]))
