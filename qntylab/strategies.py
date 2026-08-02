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

def short_horizon_reversal(close: np.ndarray, lookback: int, mode: str) -> np.ndarray:
    raw = np.zeros(len(close))
    raw[lookback:] = -np.sign(close[lookback:] / close[:-lookback] - 1)
    return _causal(np.maximum(raw, 0) if mode == "long_flat" else raw)

def volatility_scaled_moving_average(
    close: np.ndarray,
    fast: int,
    slow: int,
    realized_volatility_window: int,
    volatility_baseline_window: int,
    minimum_multiplier: float,
    maximum_multiplier: float,
    mode: str,
) -> np.ndarray:
    raw = np.zeros(len(close), dtype=float)
    kernel_fast = np.ones(fast) / fast
    kernel_slow = np.ones(slow) / slow
    ma_fast = np.convolve(close, kernel_fast, "valid")
    ma_slow = np.convolve(close, kernel_slow, "valid")
    base = np.zeros(len(close), dtype=float)
    base[slow - 1 :] = (ma_fast[slow - fast :] > ma_slow).astype(float)

    returns = np.diff(np.log(close), prepend=np.nan)
    rv = np.full(len(close), np.nan, dtype=float)
    for i in range(realized_volatility_window, len(close)):
        sample = returns[i - realized_volatility_window + 1 : i + 1]
        rv[i] = np.sqrt(8760 * np.mean(sample * sample))

    for i in range(realized_volatility_window + volatility_baseline_window, len(close)):
        baseline = np.median(rv[i - volatility_baseline_window : i])
        ratio = baseline / rv[i] if rv[i] != 0 else np.nan
        multiplier = np.clip(ratio, minimum_multiplier, maximum_multiplier)
        raw[i] = base[i] * multiplier
    return _causal(np.maximum(raw, 0) if mode == "long_flat" else raw)

def positions(family: str, close: np.ndarray, params: dict) -> np.ndarray:
    fn = {
        "H002_momentum": momentum,
        "H003_moving_average": moving_average,
        "H004_mean_reversion": mean_reversion,
        "H005_donchian": donchian,
        "H006_short_horizon_reversal": short_horizon_reversal,
        "H007_volatility_scaled_moving_average": volatility_scaled_moving_average,
    }[family]
    return fn(close, **params)
