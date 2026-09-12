"""Pure preregistration contract functions for Clean TSMOM EXP_V2.

This module has no evaluation entry point and no network or filesystem data
loader.  Decision-close timestamps are authoritative: a weight at ``t`` is
applied only to the interval immediately following close ``t``.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT",
    "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT",
]
V1_ID = "CLEAN_V1"
V2_ID = "CLEAN_V2"
MOMENTUM_LOOKBACK = 20
VOLATILITY_LOOKBACK = 90


def aggregate_8h(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int]]:
    if not rows:
        raise ValueError("empty hourly panel")
    ordered = sorted(rows, key=lambda row: int(row["timestamp"]))
    seen: set[int] = set()
    for row in ordered:
        timestamp = int(row["timestamp"])
        when = datetime.fromtimestamp(timestamp / 1000, UTC)
        if timestamp in seen or when.minute or when.second or when.microsecond:
            raise ValueError("duplicate/off-grid hour")
        seen.add(timestamp)
    output = []
    for offset in range(0, len(ordered), 8):
        group = ordered[offset : offset + 8]
        if len(group) != 8:
            raise ValueError("incomplete 8h bucket")
        stamps = [int(row["timestamp"]) for row in group]
        if stamps != list(range(stamps[0], stamps[0] + 8 * 3_600_000, 3_600_000)):
            raise ValueError("hourly gap")
        start = datetime.fromtimestamp(stamps[0] / 1000, UTC)
        if start.hour % 8:
            raise ValueError("8h bucket off-grid")
        values = {key: [float(row[key]) for row in group] for key in ("open", "high", "low", "close", "volume")}
        if any(not math.isfinite(value) for column in values.values() for value in column):
            raise ValueError("non-finite OHLCV")
        if any(value <= 0 for key in ("open", "high", "low", "close") for value in values[key]):
            raise ValueError("non-positive OHLC")
        if any(value < 0 for value in values["volume"]):
            raise ValueError("negative volume")
        if values["high"][0] < max(values["open"][0], values["low"][0]):
            raise ValueError("inconsistent OHLC")
        if values["low"][0] > min(values["open"][0], values["high"][0]):
            raise ValueError("inconsistent OHLC")
        output.append({
            "timestamp": stamps[0],
            "open": values["open"][0],
            "high": max(values["high"]),
            "low": min(values["low"]),
            "close": values["close"][-1],
            "volume": sum(values["volume"]),
        })
    return output


def signal(closes: np.ndarray, lookback: int = MOMENTUM_LOOKBACK) -> np.ndarray:
    if lookback != MOMENTUM_LOOKBACK:
        raise ValueError("momentum lookback is frozen at 20 completed 8h bars")
    output = np.zeros(len(closes), dtype=int)
    for t in range(lookback, len(closes)):
        output[t] = int(math.log(closes[t] / closes[t - lookback]) > 0)
    return output


def _check_closes(closes: np.ndarray) -> None:
    if closes.ndim != 2 or closes.shape[1] != len(SYMBOLS):
        raise ValueError(f"expected [bars,{len(SYMBOLS)}] closes")
    if np.any(~np.isfinite(closes)) or np.any(closes <= 0):
        raise ValueError("closes must be finite and positive")


def weights_v1(closes: np.ndarray) -> np.ndarray:
    """Clean V1: signal / 9, with no active-only renormalization."""
    _check_closes(closes)
    return np.column_stack([signal(closes[:, i]) for i in range(len(SYMBOLS))]) / len(SYMBOLS)


def completed_returns_at_decision_close(closes: np.ndarray, t: int) -> np.ndarray:
    """Return exactly r_(t-89)..r_t, all observable at decision close t."""
    _check_closes(closes)
    if t < VOLATILITY_LOOKBACK or t >= len(closes):
        raise ValueError("decision close lacks exactly 90 completed returns")
    returns = np.log(closes[1:] / closes[:-1])
    return returns[t - VOLATILITY_LOOKBACK : t]


def weights_v2(closes: np.ndarray) -> tuple[np.ndarray, int]:
    """Clean V2 inverse-vol weights using only returns completed by close t."""
    _check_closes(closes)
    signals = np.column_stack([signal(closes[:, i]) for i in range(len(SYMBOLS))])
    output = np.zeros_like(closes, dtype=float)
    heat_count = 0
    for t in range(VOLATILITY_LOOKBACK, len(closes)):
        returns = completed_returns_at_decision_close(closes, t)
        volatility = np.std(returns, axis=0, ddof=0)
        eligible = (signals[t] == 1) & np.isfinite(volatility) & (volatility > 0)
        indices = np.flatnonzero(eligible)
        if len(indices):
            raw = 1.0 / volatility[indices]
            target = len(indices) / len(SYMBOLS)
            output[t, indices] = target * raw / raw.sum()
            if output[t].sum() > 1.0 + 1e-15:
                output[t] *= 1.0 / output[t].sum()
                heat_count += 1
    return output, heat_count
