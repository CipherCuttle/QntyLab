from __future__ import annotations
import numpy as np

def causal(raw: np.ndarray) -> np.ndarray:
    return np.r_[0.0, raw[:-1]]

def funding_to_bars(timestamps: list[str], funding: list[dict[str, str]]) -> np.ndarray:
    """Settled F is assigned to the containing hourly bar, then causal() delays its return use."""
    index = {stamp: i for i, stamp in enumerate(timestamps)}; result = np.full(len(timestamps), np.nan)
    for event in funding:
        hour = event["timestamp"][:13] + ":00:00Z"
        if hour in index: result[index[hour]] = float(event["funding_rate"])
    return result

def zscore(values: np.ndarray, lookback: int) -> np.ndarray:
    output = np.full(len(values), np.nan)
    for i in range(lookback, len(values)):
        sample = values[i-lookback:i]; sample = sample[np.isfinite(sample)]
        # Funding is an event series (normally 8-hourly), while premium is hourly.
        # Twelve prior observations is the common minimum; calendar lookback remains
        # part of the declared definition without requiring nonexistent hourly prints.
        if len(sample) >= 12 and sample.std() > 0: output[i] = (values[i] - sample.mean()) / sample.std()
    return output

def held_signal(signal: np.ndarray, hours: int) -> np.ndarray:
    result = np.zeros(len(signal)); remaining = 0; side = 0.0
    for i, value in enumerate(signal):
        if value:
            side, remaining = value, hours
        if remaining:
            result[i] = side; remaining -= 1
    return result

def positions(family: str, close: np.ndarray, premium: np.ndarray, ofi: np.ndarray, funding: np.ndarray, params: dict) -> np.ndarray:
    raw = np.zeros(len(close))
    if family == "H007_funding_extremes":
        z = zscore(funding, params["lookback"]); raw[np.isfinite(z) & (z >= params["threshold"])] = -1; raw[np.isfinite(z) & (z <= -params["threshold"])] = 1
        raw = held_signal(raw, params["holding_hours"])
    elif family == "H008_funding_conditioned_momentum":
        momentum = np.zeros(len(close)); momentum[168:] = np.sign(close[168:] / close[:-168] - 1)
        z = zscore(funding, params["funding_lookback"]); allowed = np.isfinite(z) & (np.abs(z) <= params["max_abs_z"])
        raw = momentum * allowed
    elif family == "H009_premium_mean_reversion":
        z = zscore(premium, params["lookback"]); raw[np.isfinite(z) & (z >= params["threshold"])] = -1; raw[np.isfinite(z) & (z <= -params["threshold"])] = 1
        raw = held_signal(raw, params["holding_hours"])
    elif family == "H010_taker_flow":
        flow = np.convolve(ofi, np.ones(params["lookback"]) / params["lookback"], mode="full")[:len(ofi)]
        raw[np.abs(flow) >= params["threshold"]] = params["direction"] * np.sign(flow[np.abs(flow) >= params["threshold"]])
    else: raise ValueError(f"unknown family {family}")
    return causal(raw)

def evaluate_perp(close: np.ndarray, position: np.ndarray, timestamps: list[str], funding_events: list[dict[str, str]], fee_bps: float) -> dict:
    if len(close) != len(position): raise ValueError("matching series required")
    returns = close[1:] / close[:-1] - 1
    valid = np.array([timestamps[i][:13] != timestamps[i + 1][:13] for i in range(len(returns))], dtype=bool)
    # Exact 1h validation is done by loader; this retains the no-bridge contract if a caller supplies a gap.
    from datetime import datetime
    valid = np.array([(datetime.fromisoformat(timestamps[i + 1].replace("Z", "+00:00")) - datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))).total_seconds() == 3600 for i in range(len(returns))])
    held = position[:-1]; price = held * returns * valid
    changes = np.abs(np.diff(position)); fees = changes * fee_bps / 10_000
    funding_cash = np.zeros(len(returns)); index = {stamp[:13] + ":00:00Z": i for i, stamp in enumerate(timestamps)}
    for event in funding_events:
        hour = event["timestamp"][:13] + ":00:00Z"; bar = index.get(hour)
        if bar is not None and 0 < bar <= len(returns): funding_cash[bar - 1] += -position[bar - 1] * float(event["funding_rate"])
    net = price - fees + funding_cash
    equity = np.cumprod(1 + net); peak = np.maximum.accumulate(np.r_[1., equity])[1:]
    return {"price_pnl": float(np.prod(1 + price) - 1), "fees": float(fees.sum()), "funding_cashflow": float(funding_cash.sum()), "net_cumulative_return": float(equity[-1] - 1), "max_drawdown": float((equity / peak - 1).min()), "turnover": float(changes.sum()), "trade_count": int(np.count_nonzero(changes)), "long_exposure": float((held > 0).mean()), "short_exposure": float((held < 0).mean()), "gap_return_count": int((~valid).sum()), "net_returns": net.tolist()}
