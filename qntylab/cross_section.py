"""Small, causal cross-sectional primitives for the exploratory v2 sprint."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
import numpy as np


def deterministic_order(symbols: list[str], values: np.ndarray, descending: bool = True) -> list[int]:
    """Rank finite values, breaking ties lexicographically by symbol."""
    valid = [i for i, value in enumerate(values) if np.isfinite(value)]
    return sorted(valid, key=lambda i: ((-values[i]) if descending else values[i], symbols[i]))


def weights(symbols: list[str], score: np.ndarray, fraction: float, direction: int = 1) -> np.ndarray:
    """Equal-weight dollar-neutral top-minus-bottom book; 0 if breadth is inadequate."""
    out = np.zeros(len(symbols)); order = deterministic_order(symbols, score, descending=True)
    count = max(1, int(len(order) * fraction))
    if len(order) < 2 * count: return out
    long, short = order[:count], order[-count:]
    out[long] = direction / count; out[short] = -direction / count
    return out


def turnover(previous: np.ndarray, current: np.ndarray) -> float:
    return float(np.abs(current - previous).sum())


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 2: return float("nan")
    def ranks(values: np.ndarray) -> np.ndarray:
        order = np.argsort(values, kind="stable"); result = np.empty(len(values), dtype=float)
        result[order] = np.arange(len(values), dtype=float)
        return result
    a, b = ranks(x[mask]), ranks(y[mask])
    if a.std() == 0 or b.std() == 0: return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def factor_scores(close: np.ndarray, funding: np.ndarray | None, premium: np.ndarray | None, name: str, lookback: int) -> np.ndarray:
    """Scores at t only; caller executes the t+1 to t+2 return."""
    result = np.full_like(close, np.nan, dtype=float)
    if name in {"H012_momentum_7d", "H012_momentum_30d", "H012_momentum_90d", "H013_reversal_1d", "H013_reversal_3d"}:
        result[lookback:] = close[lookback:] / close[:-lookback] - 1
    elif name in {"H014_funding_24h", "H014_funding_7d"}:
        if funding is None: raise ValueError("funding required")
        for t in range(lookback - 1, len(close)):
            result[t] = np.nansum(funding[t - lookback + 1:t + 1])
    elif name == "H015_premium":
        if premium is None: raise ValueError("premium required")
        result[:] = premium
    else: raise ValueError(f"unknown factor {name}")
    return result


@dataclass(frozen=True)
class Evaluation:
    price_pnl: float; funding_pnl: float; fees: float; net_return: float; turnover: float
    mean_ic: float; median_ic: float; ic_hit_rate: float; daily_ics: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]


def evaluate(symbols: list[str], close: np.ndarray, score: np.ndarray, eligible: np.ndarray, funding: np.ndarray | None = None, *, fraction: float = .2, direction: int = 1, fee_bps: float = 10.) -> Evaluation:
    """Daily close decisions; t weights earn return t->t+1 and settled funding at t+1."""
    if close.shape != score.shape or close.shape != eligible.shape: raise ValueError("matching panel shapes required")
    if funding is not None and funding.shape != close.shape: raise ValueError("funding panel shape mismatch")
    prior = np.zeros(close.shape[1]); price = []; carry = []; fees = []; ics = []; history = []
    for t in range(close.shape[0] - 1):
        available = np.where(eligible[t], score[t], np.nan)
        current = weights(symbols, available, fraction, direction)
        history.append(tuple(current.tolist()))
        fee = turnover(prior, current) * fee_bps / 10_000
        forward = close[t + 1] / close[t] - 1
        valid = np.isfinite(forward) & np.isfinite(available)
        price.append(float(np.nansum(current[valid] * forward[valid])))
        carry.append(0. if funding is None else float(np.nansum(-current * np.nan_to_num(funding[t + 1], nan=0.))))
        fees.append(fee); ics.append(spearman(available, forward)); prior = current
    net = np.asarray(price) + np.asarray(carry) - np.asarray(fees)
    finite_ics = np.asarray([x for x in ics if np.isfinite(x)])
    return Evaluation(float(np.prod(1 + np.asarray(price)) - 1), float(np.sum(carry)), float(np.sum(fees)), float(np.prod(1 + net) - 1), float(np.sum(fees) * 10_000 / fee_bps if fee_bps else 0), float(finite_ics.mean()) if len(finite_ics) else float("nan"), float(np.median(finite_ics)) if len(finite_ics) else float("nan"), float((finite_ics > 0).mean()) if len(finite_ics) else float("nan"), tuple(ics), tuple(history))


def random_scores(shape: tuple[int, int], seed: int) -> np.ndarray:
    """Deterministic iid ranks; callers retain the strategy's eligibility panel."""
    return np.random.default_rng(seed).random(shape)


def receipt_sha256(spec_bytes: bytes, manifest_bytes: bytes) -> str:
    return hashlib.sha256(spec_bytes + b"\n" + manifest_bytes).hexdigest()
