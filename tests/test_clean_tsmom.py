import math
from datetime import UTC, datetime

import numpy as np
import pytest

from qntylab.clean_tsmom import SYMBOLS, aggregate_8h, signal, weights_v1, weights_v2, run_equity


def test_signal_boundary_and_causality():
    close = np.ones(23); close[20] = 2; close[21:] = 2
    out = signal(close)
    assert out[:20].sum() == 0
    assert out[20] == 1 and out[21] == 1
    zero = signal(np.ones(25)); assert zero.sum() == 0
    down = signal(np.r_[np.ones(20), np.full(5, .5)]); assert down.sum() == 0


def test_v1_alignment_and_exposure():
    close = np.ones((30, 10)); close[20:, 0] = 2; close[20:, 1:5] = 2; close[20:, 5:] = .5
    w = weights_v1(close)
    assert np.allclose(w[20, :5], .1) and np.allclose(w[20, 5:], 0)
    assert np.all(w.sum(axis=1) <= 1)


def test_v2_inverse_vol_and_future_mutation():
    x = np.ones((130, 10))
    for i in range(1, 130):
        x[i, 0] = x[i-1, 0] * 1.002
        x[i, 1] = x[i-1, 1] * (1 + (.02 if i % 2 else -.02))
        x[i, 2:] = x[i-1, 2:] * 1.001
    x[20:, :2] *= 1.01
    w1, _ = weights_v2(x); y = x.copy(); y[-1] *= 100
    w2, _ = weights_v2(y)
    assert w1[100, 0] > w1[100, 1]
    assert np.allclose(w1[:100], w2[:100])
    assert np.max(w1.sum(axis=1)) <= 1 + 1e-12


def test_aggregate_rejects_gap_duplicate_and_off_grid():
    def rows(stamps): return [{"timestamp": t, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for t in stamps]
    base = list(range(0, 8 * 3600000, 3600000))
    assert aggregate_8h(rows(base))[0]["timestamp"] == 0
    with pytest.raises(ValueError): aggregate_8h(rows(base[:-1] + [base[-1] + 7200000]))
    with pytest.raises(ValueError): aggregate_8h(rows(base[:-1] + [base[-2]]))
    with pytest.raises(ValueError): aggregate_8h(rows([3600000 + x for x in base]))


def test_funding_sign_and_costs():
    closes = np.ones((4, 10)); closes[1:, 0] = [1, 1.1, 1.1]
    weights = np.zeros_like(closes); weights[0, 0] = 0.1
    events = [{"symbol": "BTCUSDT", "timestamp": 2 * 3600000, "funding_rate": .01}]
    result = run_equity(closes, weights, [0, 3600000, 2 * 3600000, 3 * 3600000], events, "1970-01-01T00:00:00Z", "1970-01-01T04:00:00Z", .001)
    assert result["funding_paid"] > 0
    with pytest.raises(ValueError): run_equity(closes, weights, [0, 3600000, 2 * 3600000, 3 * 3600000], events * 2, "1970-01-01T00:00:00Z", "1970-01-01T04:00:00Z", .001)
