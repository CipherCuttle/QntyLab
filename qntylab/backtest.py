from __future__ import annotations
import math
import numpy as np

ANNUAL_BARS = 365 * 24

def evaluate(close: np.ndarray, position: np.ndarray, fee_bps: float) -> dict:
    if len(close) != len(position) or len(close) < 3: raise ValueError("matching close/position series of at least 3 required")
    returns = close[1:] / close[:-1] - 1; held = position[:-1]; changes = np.abs(np.diff(position))
    gross = held * returns; fees = changes * fee_bps / 10_000; net = gross - fees
    equity = np.cumprod(1 + net); peak = np.maximum.accumulate(np.r_[1.0, equity])[1:]; dd = equity / peak - 1
    mean, std = float(net.mean()), float(net.std())
    downside = net[net < 0]; downside_std = float(downside.std()) if len(downside) else 0.0
    years = len(net) / ANNUAL_BARS
    gross_total, net_total = float(np.prod(1 + gross) - 1), float(equity[-1] - 1)
    exponent = math.log1p(net_total) / years if years > 0 and 1 + net_total > 0 else None
    annual_return = float(math.expm1(exponent)) if exponent is not None and exponent < 700 else None
    # Trade is an entry or a sign flip; position changes are charged by absolute exposure.
    return {"gross_cumulative_return": gross_total, "net_cumulative_return": net_total, "annualized_return": annual_return, "annualized_volatility": std * math.sqrt(ANNUAL_BARS), "sharpe": mean / std * math.sqrt(ANNUAL_BARS) if std else None, "sortino": mean / downside_std * math.sqrt(ANNUAL_BARS) if downside_std else None, "max_drawdown": float(dd.min()), "trade_count": int(np.count_nonzero(changes)), "turnover": float(changes.sum()), "average_absolute_exposure": float(np.abs(held).mean()), "long_exposure": float((held > 0).mean()), "short_exposure": float((held < 0).mean()), "fee_cost": float(fees.sum()), "best_bar": float(net.max()), "worst_bar": float(net.min()), "net_returns": net.tolist()}

def segments(close: np.ndarray, position: np.ndarray, fee_bps: float) -> dict:
    result = {"full": evaluate(close, position, fee_bps)}
    for i, label in enumerate(("early", "middle", "late")):
        lo, hi = i * len(close) // 3, (i + 1) * len(close) // 3
        result[label] = evaluate(close[lo:hi], position[lo:hi], fee_bps)
    return result
