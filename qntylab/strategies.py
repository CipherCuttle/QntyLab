from __future__ import annotations
import numpy as np

def _causal(raw: np.ndarray) -> np.ndarray:
    """Signals known at close t become positions for bar t+1."""
    return np.r_[0.0, raw[:-1]]

def momentum(close: np.ndarray, lookback: int, mode: str) -> np.ndarray:
    raw = np.zeros(len(close)); raw[lookback:] = np.sign(close[lookback:] / close[:-lookback] - 1)
    return _causal(np.maximum(raw, 0) if mode == "long_flat" else raw)

def moving_average(close: np.ndarray, fast: int, slow: int, mode: str) -> np.ndarray:
    raw = np.zeros(len(close)); kernel_fast = np.ones(fast)/fast; kernel_slow = np.ones(slow)/slow
    ma_fast, ma_slow = np.convolve(close, kernel_fast, "valid"), np.convolve(close, kernel_slow, "valid")
    raw[slow-1:] = np.sign(ma_fast[slow-fast:] - ma_slow)
    return _causal(np.maximum(raw, 0) if mode == "long_flat" else raw)

def mean_reversion(close: np.ndarray, lookback: int, threshold: float, mode: str) -> np.ndarray:
    returns = np.diff(np.log(close), prepend=np.nan); raw = np.zeros(len(close))
    for i in range(lookback, len(close)):
        sample = returns[i-lookback:i]; std = sample.std()
        if std > 0: raw[i] = -np.sign(returns[i]) if abs(returns[i] / std) >= threshold else 0
    return _causal(np.maximum(raw, 0) if mode == "long_flat" else raw)

def donchian(close: np.ndarray, lookback: int, mode: str) -> np.ndarray:
    raw = np.zeros(len(close))
    for i in range(lookback, len(close)):
        hi, lo = close[i-lookback:i].max(), close[i-lookback:i].min()
        raw[i] = 1 if close[i] > hi else (-1 if close[i] < lo else 0)
    return _causal(np.maximum(raw, 0) if mode == "long_flat" else raw)

def positions(family: str, close: np.ndarray, params: dict) -> np.ndarray:
    fn = {"H002_momentum": momentum, "H003_moving_average": moving_average, "H004_mean_reversion": mean_reversion, "H005_donchian": donchian}[family]
    return fn(close, **params)
